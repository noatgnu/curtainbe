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

  await page.close();

  // --- Admin is Django, not Angular ---
  const adminPage = await context.newPage();
  await adminPage.goto(baseUrl + '/admin/', {
    waitUntil: 'domcontentloaded',
    timeout: 15000,
  });
  const adminTitle = await adminPage.title();
  const adminUrl = adminPage.url();
  if (adminTitle === expectedTitle) {
    fail(`/admin/ returned Angular SPA (title: "${adminTitle}") — service worker or nginx routing broken`);
  } else {
    pass(`/admin/ → Django admin (title: "${adminTitle}", final url: ${adminUrl})`);
  }
  await adminPage.close();

  // --- API is reachable ---
  const apiResp = await context.request.get(baseUrl + '/api/curtain/');
  if (apiResp.status() < 500) {
    pass(`/api/curtain/ → HTTP ${apiResp.status()}`);
  } else {
    let body = '';
    try { body = await apiResp.text(); } catch (_) {}
    fail(`/api/curtain/ → HTTP ${apiResp.status()} (server error)\n    body: ${body.slice(0, 2000)}`);
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
