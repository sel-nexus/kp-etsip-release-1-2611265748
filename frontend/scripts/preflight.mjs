/** Capture live rendered structure, accessibility snapshot, styles and reviewer screenshots. */
import { chromium } from '@playwright/test';
import { writeFile, mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true });
const captures = [];
try {
  await mkdir('../screenshots', { recursive: true });
  for (const [label, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:5173/login');
    await page.getByLabel('Email').fill('executive@ketsip.local');
    await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_DEMO_PASSWORD);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.getByRole('heading', { name: 'Executive dashboard' }).waitFor();
    await page.getByRole('region', { name: 'Executive metrics' }).waitFor();
    await page.screenshot({ path: `../screenshots/${label}-dashboard.png`, fullPage: true });
    const styles = await page.evaluate(() => {
      const body = getComputedStyle(document.body);
      const heading = getComputedStyle(document.querySelector('h1'));
      return { bodyFont: body.fontFamily, bodyColor: body.color, background: body.backgroundColor, headingSize: heading.fontSize, headingColor: heading.color };
    });
    const accessibility = page.accessibility?.snapshot ? await page.accessibility.snapshot() : await page.locator('body').ariaSnapshot();
    captures.push(`${label}\nSTYLES ${JSON.stringify(styles)}\nACCESSIBILITY ${typeof accessibility === 'string' ? accessibility : JSON.stringify(accessibility)}\nHTML\n${await page.content()}\n`);
    await context.close();
  }
  await writeFile('../ui_preflight.txt', captures.join('\n'), 'utf8');
} finally {
  await browser.close();
}
