// Development-only browser verification. Run with Playwright and Chrome installed.
const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const fs = require('fs');
const path = require('path');

async function main() {
  const base = path.resolve(process.argv[2] || path.join(__dirname, '../../Manual'));
  const evidence = path.resolve(
    process.env.B518_MANUAL_BROWSER_EVIDENCE_DIR ||
      path.join(base, '../docs/manual/evidence/browser'),
  );
  fs.mkdirSync(evidence, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    // Exercise the documented offline fallback without depending on OS
    // clipboard permission. Do not claim that clipboard contents were read back.
    await context.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: () => Promise.reject(new Error('Controlled clipboard denial')) },
      });
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const results = [];
    for (const name of ['index.html', 'index-en.html']) {
      const language = name === 'index.html' ? 'zh-Hant' : 'en';
      await page.goto(`${pathToFileURL(path.join(base, name)).href}?lang=${language}`);
      await page.locator('#maintenance').scrollIntoViewIfNeeded();
      await page.evaluate(async () => {
        const images = Array.from(document.querySelectorAll('img[src]'));
        images.forEach((image) => (image.loading = 'eager'));
        await Promise.race([
          Promise.all(images.map((image) => image.decode())),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Image loading timeout')), 15000),
          ),
        ]);
      });
      const check = await page.evaluate(() => ({
        lang: document.documentElement.lang,
        sections: Array.from(document.querySelectorAll('main section[id]')).map((item) => item.id),
        images: document.querySelectorAll('img[src]').length,
        broken: Array.from(document.querySelectorAll('img[src]'))
          .filter((image) => !image.naturalWidth)
          .map((image) => image.src),
        overflow: document.documentElement.scrollWidth > innerWidth,
      }));
      if (check.broken.length || check.overflow) throw new Error(JSON.stringify(check));
      await page.locator('#hmi').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(evidence, `manual-${name}.png`) });
      await page.locator('img.manual-image').first().click();
      await page.locator('#image-dialog').waitFor({ state: 'visible' });
      await page.keyboard.press('Escape');
      if (await page.locator('#image-dialog').isVisible()) throw new Error('Escape did not close image');
      await page.locator('#copy-report').scrollIntoViewIfNeeded();
      await page.locator('#copy-report').click();
      await page.waitForFunction(() => document.querySelector('#copy-status').textContent);
      const selected = await page.locator('#report-template').evaluate(
        (field) => field.selectionStart === 0 && field.selectionEnd === field.value.length,
      );
      if (!selected) throw new Error('Clipboard fallback did not select report');
      await page.setViewportSize({ width: 390, height: 844 });
      await page.locator('#hmi').scrollIntoViewIfNeeded();
      check.mobileOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      );
      if (check.mobileOverflow) throw new Error(`Mobile overflow: ${name}`);
      await page.screenshot({ path: path.join(evidence, `manual-mobile-${name}.png`) });
      await page.locator('.nav-toggle').click();
      if (!(await page.locator('.sidebar nav').isVisible())) throw new Error('Mobile navigation');
      await page.emulateMedia({ media: 'print' });
      if (await page.locator('.language-switch').isVisible()) throw new Error('Print language switch');
      await page.emulateMedia({ media: 'screen' });
      await page.setViewportSize({ width: 1440, height: 1000 });
      results.push(check);
    }
    if (JSON.stringify(results[0].sections) !== JSON.stringify(results[1].sections)) {
      throw new Error('Bilingual sections differ');
    }
    await page.goto(`${pathToFileURL(path.join(base, 'index.html')).href}?lang=zh-Hant#history`);
    await page.locator('#history').scrollIntoViewIfNeeded();
    await page.locator('[data-language="en"]').click();
    await page.waitForURL(/index-en.html/);
    if (!page.url().includes('#history')) throw new Error('Section not preserved');
    const nojs = await browser.newContext({ javaScriptEnabled: false });
    const plain = await nojs.newPage();
    await plain.goto(pathToFileURL(path.join(base, 'index.html')).href);
    if (!(await plain.locator('#history').isVisible())) throw new Error('No JavaScript content');
    await nojs.close();
    if (errors.length) throw new Error(errors.join('\n'));
    const report = JSON.stringify(
      {
        results,
        checks: ['offline images', 'desktop/mobile overflow', 'image dialog/Escape',
          'clipboard denial fallback and report selection', 'mobile nav', 'print styles', 'language anchor', 'no JavaScript'],
        errors,
      },
      null,
      2,
    );
    fs.writeFileSync(path.join(evidence, 'validation.json'), `${report}\n`);
    console.log(report);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
