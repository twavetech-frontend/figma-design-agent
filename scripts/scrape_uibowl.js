#!/usr/bin/env node
/**
 * Scrape uibowl.io for an app's full screen catalog.
 *
 * Usage:
 *   node scripts/scrape_uibowl.js <appName> [outputDir]
 *
 * Default output: references/uibowl/<appName>/
 *
 * Strategy:
 *   1. Open https://uibowl.io/name/<appName>
 *   2. Wait for grid to render
 *   3. Auto-scroll to load all infinite-scroll pages
 *   4. Intercept network calls to /api/v2/apps/images and /api/v2/apps/patterns,
 *      collect their JSON payloads (these contain imgId + image URL + metadata)
 *   5. Save:
 *      - <outputDir>/index.json — array of {imgId, title, category, patternName,
 *                                            patternCode, app, imageUrl, localPath}
 *      - <outputDir>/<imgId>.webp — downloaded image
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const https = require('https');

const APP_NAME = process.argv[2] || '토스';
const OUT_DIR = process.argv[3] ||
  path.join(__dirname, '..', 'references', 'uibowl', APP_NAME);

async function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (res) => {
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode} ${url}`));
      }
      res.pipe(file);
      file.on('finish', () => file.close(resolve));
    }).on('error', (err) => {
      fs.unlinkSync(dest);
      reject(err);
    });
  });
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`[scrape] target: ${APP_NAME}`);
  console.log(`[scrape] output: ${OUT_DIR}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
  });
  const page = await context.newPage();

  // Collect all API responses
  const records = new Map(); // imgId → record
  const apiCalls = []; // debug: all api urls hit
  page.on('response', async (resp) => {
    const url = resp.url();
    if (!/\/api\//.test(url)) return;
    if (resp.status() !== 200) return;
    apiCalls.push(url);
    try {
      const json = await resp.json();
      // Walk recursively to find image/pattern records
      const walkRows = (rows) => {
        if (!Array.isArray(rows)) return;
        for (const row of rows) {
          if (!row || typeof row !== 'object') continue;
          const imgId = row.imgId || row.id;
          if (!imgId) continue;
          const imageUrl = row.img || row.imageUrl
                          || (row.images && row.images[0])
                          || (Array.isArray(row.imgs) && row.imgs[0]);
          if (!imageUrl) continue;
          const appName = (row.app && row.app.name) || row.appName;
          if (records.has(imgId)) continue;
          records.set(imgId, {
            imgId,
            title: row.title || row.imgTitle || '',
            category: row.app && row.app.categoryName,
            patternName: row.patternName || '',
            patternCode: row.patternCode,
            patternCodeName: row.patternCodeName || '',
            app: { id: row.app && row.app.id, name: appName || APP_NAME },
            imageUrl,
            createdAt: row.createdAt,
          });
        }
      };
      if (json) {
        if (Array.isArray(json.data)) walkRows(json.data);
        else if (json.data && typeof json.data === 'object') {
          for (const v of Object.values(json.data)) walkRows(v);
        }
      }
    } catch {}
  });
  page.on('requestfinished', (req) => {
    if (/\/api\//.test(req.url())) {
      // helpful for debug
    }
  });

  await page.goto(`https://uibowl.io/name/${encodeURIComponent(APP_NAME)}`, {
    waitUntil: 'networkidle', timeout: 60000,
  });

  // Wait for initial render
  await page.waitForTimeout(3000);

  // Auto-scroll to bottom repeatedly until no new content
  let lastCount = 0;
  let stableRounds = 0;
  for (let i = 0; i < 80 && stableRounds < 3; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1500);
    const cur = records.size;
    if (cur === lastCount) {
      stableRounds++;
    } else {
      stableRounds = 0;
      lastCount = cur;
    }
    process.stdout.write(`\r[scrape] iteration ${i+1}: ${cur} records  `);
  }
  process.stdout.write('\n');

  console.log(`[debug] api calls: ${apiCalls.length}`);
  for (const u of apiCalls.slice(0, 20)) console.log(`  ${u}`);

  await browser.close();

  console.log(`[scrape] collected ${records.size} unique records`);

  // Download images
  const index = [];
  let downloaded = 0;
  for (const r of records.values()) {
    if (!r.imageUrl) continue;
    const safeId = r.imgId.replace(/[^a-zA-Z0-9_-]/g, '_');
    const ext = (r.imageUrl.match(/\.(webp|png|jpe?g)/i) || ['', 'webp'])[1].toLowerCase();
    const localPath = path.join(OUT_DIR, `${safeId}.${ext}`);
    if (!fs.existsSync(localPath)) {
      try {
        await downloadFile(r.imageUrl, localPath);
        downloaded++;
        if (downloaded % 10 === 0) process.stdout.write(`\r[dl] ${downloaded}  `);
      } catch (e) {
        console.warn(`\n[dl] FAIL ${r.imgId}: ${e.message}`);
        continue;
      }
    }
    index.push({ ...r, localPath: path.relative(path.dirname(OUT_DIR), localPath) });
  }
  process.stdout.write(`\n[dl] downloaded ${downloaded} images\n`);

  fs.writeFileSync(
    path.join(OUT_DIR, 'index.json'),
    JSON.stringify({
      appName: APP_NAME,
      count: index.length,
      scrapedAt: new Date().toISOString(),
      records: index,
    }, null, 2),
  );

  console.log(`[scrape] index written: ${path.join(OUT_DIR, 'index.json')}`);
})().catch((e) => {
  console.error('[scrape] FATAL', e);
  process.exit(1);
});
