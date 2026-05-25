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
  // Clear cookies so the Django admin session set earlier in testVhost does not cause DRF's
  // SessionAuthentication to enforce CSRF on the POST /user/ call inside the Angular login flow.
  await context.clearCookies();

  const page = await context.newPage();
  await page.goto(baseUrl + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('footer', { timeout: 20000 });

  // Wait for the Session dropdown toggle — present in both Curtain and CurtainPTM once the
  // navbar component mounts. The Login item lives inside this dropdown in both apps.
  const sessionToggleReady = await page.waitForSelector('#dropdownSession', { timeout: 15000 })
    .then(() => true).catch(() => false);
  if (!sessionToggleReady) {
    fail('Angular navbar did not render — #dropdownSession not found within 15 s');
    await page.close();
    return;
  }

  // Open the Session dropdown and click the Login item inside it.
  await page.click('#dropdownSession');

  // The Login button is a .dropdown-item inside the now-open Session menu.
  const loginBtn = page.locator('button.dropdown-item', { hasText: 'Login' }).first();
  const loginVisible = await loginBtn.waitFor({ state: 'visible', timeout: 5000 })
    .then(() => true).catch(() => false);

  if (!loginVisible) {
    fail('Login item not visible inside #dropdownSession menu');
    await page.close();
    return;
  }

  await loginBtn.click();

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
  // Scope to ngb-modal-window to avoid matching any other submit button in the page DOM.
  await page.locator('ngb-modal-window button[type=submit]').click();

  // Login succeeds when modal closes (username input disappears)
  const modalClosed = await usernameInput.waitFor({ state: 'hidden', timeout: 15000 })
    .then(() => true).catch(() => false);

  if (modalClosed) {
    pass('frontend UI login succeeded — modal closed');
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
