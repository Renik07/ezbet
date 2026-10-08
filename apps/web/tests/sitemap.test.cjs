const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const ts = require('typescript');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ezbet-sitemap-tests-'));
process.env.EZBET_PUBLIC_CACHE_DIR = path.join(dir, 'cache');
process.env.EZBET_API_BASE_URL = 'https://fixture.example';
for (const name of ['api', 'public-data-cache', 'sitemap']) {
  fs.writeFileSync(path.join(dir, `${name}.js`), ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib', `${name}.ts`), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }
  }).outputText);
}
fs.writeFileSync(path.join(dir, 'site.js'), 'exports.absoluteUrl = path => "https://ezbet.ru" + path;');
for (const [name, file] of [['index', 'sitemap.xml/route.ts'], ['part', 'sitemaps/[part]/route.ts']]) {
  const source = fs.readFileSync(path.join(__dirname, '../app', file), 'utf8').replaceAll('@/lib/sitemap', './sitemap').replaceAll('@/lib/site', './site');
  fs.writeFileSync(path.join(dir, `${name}.js`), ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  }).outputText);
}
const index = require(path.join(dir, 'index.js'));
const part = require(path.join(dir, 'part.js'));
const { publicDataCache } = require(path.join(dir, 'public-data-cache.js'));
after(() => fs.rmSync(dir, { recursive: true, force: true }));

test('200,000 links use a small index and fetch only the requested 1000-link range', async () => {
  const requests = [];
  global.fetch = async (url) => {
    requests.push(url);
    const items = url.endsWith('/sitemap') ? Array.from({ length: 200 }, (_, id) => ({ id, updatedAt: '2026-10-08T10:00:00Z' })) :
      Array.from({ length: 1000 }, (_, i) => ({ slug: `article-${199000 + i}`, updatedAt: '2026-10-08T10:00:00Z' }));
    return new Response(JSON.stringify({ items }));
  };
  let result = await index.GET();
  assert.equal(result.status, 200);
  const xml = await result.text();
  assert.equal((xml.match(/<sitemap>/g) || []).length, 201);
  assert.ok(xml.includes('https://ezbet.ru/sitemaps/199.xml'));
  assert.equal(requests.length, 1);
  result = await part.GET(new Request('https://ezbet.ru/sitemaps/199.xml'), { params: Promise.resolve({ part: '199.xml' }) });
  assert.equal(result.status, 200);
  assert.equal(((await result.text()).match(/<url>/g) || []).length, 1000);
  assert.equal(requests.length, 2);
  await part.GET(new Request('https://ezbet.ru/sitemaps/199.xml'), { params: Promise.resolve({ part: '199.xml' }) });
  assert.equal(requests.length, 2);
});

test('cold outage is 503 rather than an empty successful sitemap; invalid range is 404', async () => {
  await publicDataCache.clear();
  global.fetch = async () => { throw new Error('offline'); };
  assert.equal((await index.GET()).status, 503);
  assert.equal((await part.GET(new Request('https://ezbet.ru'), { params: Promise.resolve({ part: '0.xml' }) })).status, 503);
  assert.equal((await part.GET(new Request('https://ezbet.ru'), { params: Promise.resolve({ part: '-1.xml' }) })).status, 404);
});
