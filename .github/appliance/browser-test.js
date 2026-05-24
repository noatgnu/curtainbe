/**
 * Playwright browser smoke tests for the Curtain appliance.
 *
 * Usage:
 *   node browser-test.js <curtain-base-url> <curtainptm-base-url>
 *
 * Example:
 *   node browser-test.js https://localhost:8443 https://curtainptm.local
 */

const { chromium } = require('playwright');

const [, , curtainUrl = 'https://curtain.local', ptmUrl = 'https://curtainptm.local'] =
  process.argv;

const passed = [];
const failed = [];

function pass(msg) {
  console.log('  PASS:', msg);
  passed.push(msg);
}

function fail(msg) {
  console.error('  FAIL:', msg);
  failed.push(msg);
}

async function waitForServiceWorker(page, timeoutMs = 15000) {
  return Promise.race([
    page.evaluate(() =>
      typeof navigator.serviceWorker === 'undefined'
        ? Promise.resolve()
        : navigator.serviceWorker.ready.then(() => new Promise(resolve => {
            if (navigator.serviceWorker.controller) return resolve();
            navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true });
          }))
    ),
    new Promise(resolve => setTimeout(resolve, timeoutMs)),
  ]);
}

/**
 * Test frontend login via the Angular UI modal.
 * Curtain exposes a direct "Login" button in the navbar;
 * CurtainPTM hides it inside a dropdown — try both.
 */
async function testFrontendLogin(context, baseUrl) {
  // --- API-level credential check ---
  const tokenResp = await context.request.post(baseUrl + '/token/', {
    data: { username: 'admin', password: 'Curtain123' },
    headers: { 'Content-Type': 'application/json' },
  });
  if (tokenResp.status() === 200) {
    pass('credentials valid — /token/ returned 200');
  } else {
    let body = '';
    try { body = await tokenResp.text(); } catch (_) {}
    fail(`credentials rejected — /token/ returned ${tokenResp.status()}\n    body: ${body.slice(0, 500)}`);
    return;
  }

  // --- Frontend UI login ---
  const page = await context.newPage();
  await page.goto(baseUrl + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('footer', { timeout: 20000 });

  // Wait for Angular navbar to render (dropdown toggles are always present once the component mounts).
  // Do NOT wait for the Login button itself — NgBootstrap renders dropdown menus lazily so the
  // button may not be in the DOM until its parent dropdown is opened for the first time.
  const navbarReady = await page.waitForSelector('[ngbDropdownToggle]', { timeout: 15000 })
    .then(() => true).catch(() => false);
  if (!navbarReady) {
    fail('Angular navbar did not render — no dropdown toggles found within 15 s');
    await page.close();
    return;
  }

  const loginBtn = page.locator('button:has-text("Login")').first();

  // Try direct visibility first (standalone Login button in navbar), then fall through to
  // opening each dropdown in reverse order until the Login item becomes visible.
  let clicked = false;
  if (await loginBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
    await loginBtn.click();
    clicked = true;
  } else {
    const toggles = page.locator('[ngbDropdownToggle]');
    const count = await toggles.count();
    for (let i = count - 1; i >= 0; i--) {
      const toggle = toggles.nth(i);
      if (!await toggle.isVisible().catch(() => false)) continue;
      await toggle.click();
      if (await loginBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
        await loginBtn.click();
        clicked = true;
        break;
      }
      await toggle.click();
    }
  }
  if (!clicked) {
    fail('could not find and click Login button — not visible in navbar or any dropdown');
    await page.close();
    return;
  }

  // Wait for modal inputs
  const usernameInput = page.locator('#username');
  const modalOpened = await usernameInput.waitFor({ timeout: 10000 }).then(() => true).catch(() => false);
  if (!modalOpened) {
    fail('frontend login modal did not open');
    await page.close();
    return;
  }

  await page.fill('#username', 'admin');
  await page.fill('#password', 'Curtain123');
  await page.locator('button[type=submit]').first().click();

  // Login succeeds when modal closes (username input disappears)
  const modalClosed = await usernameInput.waitFor({ state: 'hidden', timeout: 15000 })
    .then(() => true).catch(() => false);

  if (modalClosed) {
    // Confirm the Login button is gone (user is now authenticated)
    const loginGone = await page.locator('button:has-text("Login")').count() === 0;
    if (loginGone) {
      pass('frontend UI login succeeded — Login button no longer visible');
    } else {
      const errText = await page.locator('.alert-danger').textContent().catch(() => '');
      fail(`frontend UI login — modal closed but Login button still present (${errText.trim()})`);
    }
  } else {
    const errText = await page.locator('.alert-danger').textContent().catch(() => '');
    fail(`frontend UI login failed — modal did not close (${errText.trim() || 'no error shown'})`);
  }

  await page.close();
}

async function testVhost(context, baseUrl, expectedTitle) {
  console.log(`\nTesting ${baseUrl}`);

  const fontFailures = [];
  const page = await context.newPage();

  page.on('requestfailed', (req) => {
    if (/\.(woff2?|ttf|eot)(\?|$)/.test(req.url())) {
      fontFailures.push(`${req.url()} — ${req.failure().errorText}`);
    }
  });

  // --- Frontend loads with correct title ---
  await page.goto(baseUrl + '/', { waitUntil: 'networkidle', timeout: 30000 });

  const angularRendered = await page.waitForSelector('footer', { timeout: 20000 })
    .then(() => true).catch(() => false);
  if (!angularRendered) {
    const bodySnippet = await page.evaluate(() => document.body.innerHTML.slice(0, 1000));
    fail(`Angular did not render within 20 s — app may have crashed\n    body: ${bodySnippet}`);
  }

  const frontendTitle = await page.title();
  if (frontendTitle === expectedTitle) {
    pass(`frontend title "${frontendTitle}"`);
  } else {
    fail(`frontend title: expected "${expectedTitle}", got "${frontendTitle}"`);
  }

  // --- Bootstrap icons font loaded ---
  if (fontFailures.length > 0) {
    fail(`font request(s) failed:\n    ${fontFailures.join('\n    ')}`);
  } else {
    pass('no font request failures');
  }

  const fontLoaded = await page.evaluate(() =>
    document.fonts.ready.then(() => document.fonts.check('12px "bootstrap-icons"'))
  );
  if (fontLoaded) {
    pass('bootstrap-icons font resolved by browser');
  } else {
    fail('bootstrap-icons font not resolved (check /media/ serving)');
  }

  // --- Admin link points to /admin/ ---
  const adminLinkResult = await page.evaluate(() => {
    const anchors = Array.from(document.querySelectorAll('a[href]'));
    const adminAnchor = anchors.find(a => {
      const href = a.getAttribute('href') || '';
      return href === '/admin' || href === '/admin/' || href.endsWith('/admin') || href.endsWith('/admin/');
    });
    if (adminAnchor) return { found: true, href: adminAnchor.getAttribute('href') };
    return { found: false, allHrefs: anchors.map(a => a.getAttribute('href')) };
  });

  if (!adminLinkResult.found) {
    fail(`no link pointing to /admin/ found\n    all hrefs in page: ${JSON.stringify(adminLinkResult.allHrefs)}`);
  } else if (adminLinkResult.href === '/admin' || adminLinkResult.href === '/admin/') {
    pass(`admin link href "${adminLinkResult.href}"`);
  } else {
    fail(`admin link href "${adminLinkResult.href}" — expected /admin/ (apiURL leaking into href?)`);
  }

  // --- Wait for service worker to activate ---
  await waitForServiceWorker(page);
  await page.reload({ waitUntil: 'networkidle', timeout: 20000 });

  await page.close();

  // --- /admin/ serves Django, not Angular SPA ---
  const adminPage = await context.newPage();
  await adminPage.goto(baseUrl + '/admin/', { waitUntil: 'domcontentloaded', timeout: 20000 });
  const adminTitle = await adminPage.title();
  const adminUrl = adminPage.url();

  if (adminTitle === expectedTitle) {
    fail(`/admin/ returned Angular SPA (title: "${adminTitle}") — service worker intercepting /admin/`);
  } else {
    pass(`/admin/ → Django admin (title: "${adminTitle}", url: ${adminUrl})`);
  }

  const hasDjangoForm = await adminPage.locator('#login-form, #id_username, .login').count() > 0;
  if (hasDjangoForm) {
    pass('/admin/ contains Django login form');
  } else {
    fail('/admin/ missing Django login form');
  }

  // --- Django admin login ---
  if (hasDjangoForm) {
    await adminPage.fill('#id_username', 'admin');
    await adminPage.fill('#id_password', 'Curtain123');
    await Promise.all([
      adminPage.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }),
      adminPage.click('[type=submit]'),
    ]);
    const afterLoginUrl = adminPage.url();
    const afterLoginTitle = await adminPage.title();
    if (afterLoginUrl.includes('/admin/login/')) {
      fail(`Django admin login failed — still on login page (title: "${afterLoginTitle}")`);
    } else {
      pass(`Django admin login succeeded → ${afterLoginUrl}`);
    }
  }

  await adminPage.close();

  // --- Frontend UI login ---
  await testFrontendLogin(context, baseUrl);

  // --- API is reachable ---
  const apiResp = await context.request.get(baseUrl + '/curtain/');
  if (apiResp.status() < 500) {
    pass(`/curtain/ → HTTP ${apiResp.status()}`);
  } else {
    let body = '';
    try { body = await apiResp.text(); } catch (_) {}
    fail(`/curtain/ → HTTP ${apiResp.status()} (server error)\n    body: ${body.slice(0, 2000)}`);
  }

  // --- Static assets reachable ---
  const staticResp = await context.request.get(baseUrl + '/static/rest_framework/js/default.js');
  if (staticResp.status() === 200) {
    pass(`/static/ served correctly (HTTP ${staticResp.status()})`);
  } else {
    fail(`/static/ returned HTTP ${staticResp.status()}`);
  }
}

(async () => {
  const browser = await chromium.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    await testVhost(context, curtainUrl, 'Curtain 2.0');
    await testVhost(context, ptmUrl, 'CurtainPTM');

    await context.close();
  } finally {
    await browser.close();
  }

  console.log(`\nResults: ${passed.length} passed, ${failed.length} failed`);
  if (failed.length > 0) {
    console.error('\nFailed:\n  ' + failed.join('\n  '));
    process.exit(1);
  }
})().catch((err) => {
  console.error('\nUnhandled error:', err.message);
  process.exit(1);
});
