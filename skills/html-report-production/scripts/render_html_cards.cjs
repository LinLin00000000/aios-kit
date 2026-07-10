#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { pathToFileURL } = require('url');

function parseArgs(argv) {
  const out = {
    selector: '[data-card-name]',
    viewportWidth: 1200,
    viewportHeight: 900,
    deviceScaleFactor: 2,
    exportWidth: 960,
    pagePadding: 24,
    clean: false,
    manifest: null,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === '--clean') out.clean = true;
    else if (key === '--input') out.input = argv[++i];
    else if (key === '--output-dir') out.outputDir = argv[++i];
    else if (key === '--selector') out.selector = argv[++i];
    else if (key === '--viewport-width') out.viewportWidth = Number(argv[++i]);
    else if (key === '--viewport-height') out.viewportHeight = Number(argv[++i]);
    else if (key === '--dpr') out.deviceScaleFactor = Number(argv[++i]);
    else if (key === '--export-width') out.exportWidth = Number(argv[++i]);
    else if (key === '--page-padding') out.pagePadding = Number(argv[++i]);
    else if (key === '--manifest') out.manifest = argv[++i];
    else throw new Error(`Unknown argument: ${key}`);
  }
  if (!out.input || !out.outputDir) {
    throw new Error('Usage: render_html_cards.cjs --input report.html --output-dir cards [--selector "[data-card-name]"] [--export-width 960] [--dpr 2] [--clean]');
  }
  for (const [name, value] of Object.entries({
    viewportWidth: out.viewportWidth,
    viewportHeight: out.viewportHeight,
    deviceScaleFactor: out.deviceScaleFactor,
    exportWidth: out.exportWidth,
    pagePadding: out.pagePadding,
  })) {
    if (!Number.isFinite(value) || value <= 0) throw new Error(`Invalid ${name}: ${value}`);
  }
  return out;
}

function loadPlaywright() {
  const roots = [
    process.env.PLAYWRIGHT_NODE_MODULES,
    execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim(),
    path.join(os.homedir(), '.hermes', 'node', 'lib', 'node_modules'),
    '/usr/local/lib/node_modules',
  ].filter(Boolean);
  for (const root of [...new Set(roots)]) {
    const candidate = path.join(root, 'playwright');
    if (fs.existsSync(path.join(candidate, 'package.json'))) return require(candidate);
  }
  throw new Error(`Global Playwright package not found. Checked: ${roots.join(', ')}`);
}

function safeSlug(value, fallback) {
  const slug = String(value || '')
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
  return slug || fallback;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const input = path.resolve(args.input);
  const outputDir = path.resolve(args.outputDir);
  if (!fs.existsSync(input) || !fs.statSync(input).isFile()) throw new Error(`Input HTML not found: ${input}`);
  fs.mkdirSync(outputDir, { recursive: true });
  if (args.clean) {
    for (const name of fs.readdirSync(outputDir)) {
      if (/^\d{2,3}-.*\.png$/i.test(name)) fs.rmSync(path.join(outputDir, name));
    }
  }

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const browserVersion = await browser.version();
  const browserMajor = browserVersion.split('.')[0];
  const userAgent = `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${browserMajor}.0.0.0 Safari/537.36`;
  const context = await browser.newContext({
    viewport: { width: args.viewportWidth, height: args.viewportHeight },
    deviceScaleFactor: args.deviceScaleFactor,
    userAgent,
    locale: 'zh-CN',
    colorScheme: 'light',
  });

  try {
    const page = await context.newPage();
    const consoleErrors = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    page.on('pageerror', error => consoleErrors.push(String(error)));
    await page.goto(pathToFileURL(input).href, { waitUntil: 'load' });
    await page.emulateMedia({ media: 'screen' });
    await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}' });
    await page.evaluate(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; });

    const geometry = await page.evaluate((selector) => {
      const cards = [...document.querySelectorAll(selector)];
      const overflowing = [...document.querySelectorAll('.table-wrap, pre')]
        .filter(el => el.scrollWidth > el.clientWidth + 1)
        .map(el => ({ tag: el.tagName, className: el.className, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
      return {
        cardCount: cards.length,
        bodyScrollWidth: document.body.scrollWidth,
        bodyClientWidth: document.body.clientWidth,
        pageScrollHeight: document.documentElement.scrollHeight,
        horizontalPageOverflow: document.body.scrollWidth > document.body.clientWidth + 1,
        overflowing,
      };
    }, args.selector);

    if (geometry.cardCount === 0) throw new Error(`No cards matched selector: ${args.selector}`);
    if (geometry.horizontalPageOverflow || geometry.overflowing.length) {
      throw new Error(`Layout overflow detected: ${JSON.stringify(geometry)}`);
    }

    const cards = page.locator(args.selector);
    const exported = [];
    for (let i = 0; i < geometry.cardCount; i += 1) {
      await cards.evaluateAll((elements, options) => {
        elements.forEach((element, index) => {
          element.style.display = index === options.activeIndex ? '' : 'none';
          if (index === options.activeIndex) element.style.margin = '0';
        });
        const main = document.querySelector('main');
        if (main) main.style.cssText = `width:${options.exportWidth}px;margin:0 auto;padding:${options.pagePadding}px;`;
        document.documentElement.style.background = getComputedStyle(document.body).backgroundColor;
      }, { activeIndex: i, exportWidth: args.exportWidth, pagePadding: args.pagePadding });
      await page.setViewportSize({ width: args.exportWidth, height: 900 });
      const card = cards.nth(i);
      const box = await card.boundingBox();
      if (!box || box.width <= 0 || box.height <= 0) throw new Error(`Card ${i + 1} has invalid geometry`);
      const meta = await card.evaluate(el => ({
        name: el.getAttribute('data-card-name'),
        title: (el.querySelector('h1,h2')?.textContent || '').replace(/\s+/g, ' ').trim(),
      }));
      const height = Math.ceil(box.height + args.pagePadding * 2);
      await page.setViewportSize({ width: args.exportWidth, height });
      const index = String(i + 1).padStart(2, '0');
      const name = `${index}-${safeSlug(meta.name, 'card')}.png`;
      const output = path.join(outputDir, name);
      await page.screenshot({ path: output, type: 'png' });
      exported.push({
        index: i + 1,
        name,
        title: meta.title,
        cssPixels: { width: args.exportWidth, height },
        outputPixels: { width: Math.round(args.exportWidth * args.deviceScaleFactor), height: Math.round(height * args.deviceScaleFactor) },
      });
    }

    const result = {
      input,
      outputDir,
      selector: args.selector,
      browser: await browser.version(),
      userAgent,
      viewport: { width: args.viewportWidth, height: args.viewportHeight, deviceScaleFactor: args.deviceScaleFactor },
      geometry,
      consoleErrors,
      cards: exported,
    };
    if (consoleErrors.length) throw new Error(`Browser console errors: ${JSON.stringify(consoleErrors)}`);
    if (args.manifest) {
      const manifest = path.resolve(args.manifest);
      fs.mkdirSync(path.dirname(manifest), { recursive: true });
      fs.writeFileSync(manifest, JSON.stringify(result, null, 2) + '\n');
    }
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exit(1);
});
