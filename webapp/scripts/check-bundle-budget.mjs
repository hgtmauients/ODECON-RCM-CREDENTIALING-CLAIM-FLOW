import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';
import { gzipSync } from 'node:zlib';

const distAssetsDir = process.env.BUNDLE_BUDGET_ASSETS_DIR
  ? join(process.cwd(), process.env.BUNDLE_BUDGET_ASSETS_DIR)
  : join(process.cwd(), 'dist', 'assets');

const budgets = {
  maxJsChunkGzipKb: Number(process.env.BUNDLE_BUDGET_MAX_JS_CHUNK_GZIP_KB || 420),
  maxTotalJsGzipKb: Number(process.env.BUNDLE_BUDGET_MAX_TOTAL_JS_GZIP_KB || 700),
  maxTotalCssGzipKb: Number(process.env.BUNDLE_BUDGET_MAX_TOTAL_CSS_GZIP_KB || 140),
  maxTotalAssetsRawKb: Number(process.env.BUNDLE_BUDGET_MAX_TOTAL_ASSETS_RAW_KB || 2300),
};

const files = readdirSync(distAssetsDir);
const jsFiles = files.filter((f) => extname(f) === '.js');
const cssFiles = files.filter((f) => extname(f) === '.css');

function toKb(bytes) {
  return bytes / 1024;
}

function gzipSize(filePath) {
  return gzipSync(readFileSync(filePath), { level: 9 }).length;
}

let maxJsChunkGzip = 0;
let totalJsGzip = 0;
let totalCssGzip = 0;
let totalAssetsRaw = 0;

for (const file of files) {
  const fullPath = join(distAssetsDir, file);
  totalAssetsRaw += statSync(fullPath).size;
}

for (const file of jsFiles) {
  const fullPath = join(distAssetsDir, file);
  const gz = gzipSize(fullPath);
  totalJsGzip += gz;
  if (gz > maxJsChunkGzip) maxJsChunkGzip = gz;
}

for (const file of cssFiles) {
  const fullPath = join(distAssetsDir, file);
  totalCssGzip += gzipSize(fullPath);
}

const metrics = {
  maxJsChunkGzipKb: Number(toKb(maxJsChunkGzip).toFixed(2)),
  totalJsGzipKb: Number(toKb(totalJsGzip).toFixed(2)),
  totalCssGzipKb: Number(toKb(totalCssGzip).toFixed(2)),
  totalAssetsRawKb: Number(toKb(totalAssetsRaw).toFixed(2)),
};

console.log('Bundle budget metrics:', JSON.stringify(metrics));
console.log('Bundle budget limits:', JSON.stringify(budgets));

const failures = [];
if (metrics.maxJsChunkGzipKb > budgets.maxJsChunkGzipKb) {
  failures.push(`maxJsChunkGzipKb ${metrics.maxJsChunkGzipKb} > ${budgets.maxJsChunkGzipKb}`);
}
if (metrics.totalJsGzipKb > budgets.maxTotalJsGzipKb) {
  failures.push(`totalJsGzipKb ${metrics.totalJsGzipKb} > ${budgets.maxTotalJsGzipKb}`);
}
if (metrics.totalCssGzipKb > budgets.maxTotalCssGzipKb) {
  failures.push(`totalCssGzipKb ${metrics.totalCssGzipKb} > ${budgets.maxTotalCssGzipKb}`);
}
if (metrics.totalAssetsRawKb > budgets.maxTotalAssetsRawKb) {
  failures.push(`totalAssetsRawKb ${metrics.totalAssetsRawKb} > ${budgets.maxTotalAssetsRawKb}`);
}

if (failures.length > 0) {
  console.error('Bundle budget check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Bundle budget check passed.');
