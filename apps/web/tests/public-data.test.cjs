const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const ts = require('typescript');
const { mkdtempSync, readFileSync, writeFileSync } = require('node:fs');

// Compile the actual loaders with the project's existing TypeScript dependency.
const compiled = mkdtempSync(path.join(os.tmpdir(), 'ezbet-web-tests-'));
process.env.EZBET_PUBLIC_CACHE_DIR = path.join(compiled, 'singleton');
for (const name of ['api', 'public-data-cache', 'news', 'forecasts']) {
  const source = readFileSync(path.join(__dirname, '../lib', `${name}.ts`), 'utf8');
  writeFileSync(path.join(compiled, `${name}.js`), ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }
  }).outputText);
}
const { PublicDataCache, PublicApiError, publicDataCache } = require(path.join(compiled, 'public-data-cache.js'));
const { getNews, getArticle } = require(path.join(compiled, 'news.js'));
const { getTodayForecasts, getLiveForecast } = require(path.join(compiled, 'forecasts.js'));
after(() => fs.rm(compiled, { recursive: true, force: true }));
const url = 'https://fixture.example/api/v1/news';
const policy = { freshMs: 60_000, staleMs: 900_000 };
const validate = (data) => { assert.equal(typeof data.value, 'number'); return data; };
const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
const newsItem = { id: 'real-news', title: 'Real title', description: 'Real description', category: 'football',
  source: 'Real source', publishedAt: '2026-10-08T10:00:00Z', aiReviewed: true, articleSlug: 'real-slug' };

async function fixture(t, options = {}) {
  const directory = await fs.mkdtemp(path.join(compiled, 'cache-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  let now = 1_000_000;
  let calls = 0;
  let behavior = () => response({ value: 7 });
  const cache = new PublicDataCache({ directory, now: () => now, fetcher: async (...args) => { calls++; return behavior(...args); }, ...options });
  return { cache, directory, setTime: (value) => { now = value; }, setFetch: (callback) => { behavior = callback; }, calls: () => calls };
}

function liveEnvironment(t) {
  const previous = { ...process.env };
  process.env.EZBET_API_BASE_URL = 'https://fixture.example';
  delete process.env.NEXT_PUBLIC_API_BASE_URL;
  process.env.NODE_ENV = 'production';
  t.after(async () => { process.env = previous; await publicDataCache.clear(); });
}

test('fresh responses share one request and disk snapshots survive cache recreation', async (t) => {
  const f = await fixture(t);
  const results = await Promise.all(Array.from({ length: 8 }, () => f.cache.get(url, validate, policy)));
  assert.ok(results.every((result) => result.data.value === 7));
  assert.equal(f.calls(), 1);
  const restarted = new PublicDataCache({ directory: f.directory, now: () => 1_000_001, fetcher: () => { throw Error('must not fetch'); } });
  assert.equal((await restarted.get(url, validate, policy)).source, 'cache');
});

test('outage serves real snapshots only within a deadline that failures never extend', async (t) => {
  const f = await fixture(t);
  await f.cache.get(url, validate, policy);
  f.setTime(1_060_001);
  f.setFetch(() => { throw Error('offline'); });
  assert.equal((await f.cache.get(url, validate, policy)).source, 'stale');
  const calls = f.calls();
  await f.cache.get(url, validate, policy);
  assert.equal(f.calls(), calls); // retry backoff
  f.setTime(1_900_001);
  await assert.rejects(f.cache.get(url, validate, policy), PublicApiError);
});

test('authoritative 404 removes persisted article snapshots instead of reviving deleted data', async (t) => {
  const f = await fixture(t);
  const articleUrl = 'https://fixture.example/api/v1/articles/real-slug';
  await f.cache.get(articleUrl, validate, policy);
  f.setTime(1_060_001);
  f.setFetch(() => response({}, 404));
  await assert.rejects(f.cache.get(articleUrl, validate, policy), (error) => error.status === 404);
  assert.equal((await fs.readdir(f.directory)).length, 0);
});

test('invalid API JSON cannot replace the last valid snapshot', async (t) => {
  const f = await fixture(t);
  await f.cache.get(url, validate, policy);
  f.setTime(1_060_001);
  f.setFetch(() => response({ value: 'invalid' }));
  assert.equal((await f.cache.get(url, validate, policy)).data.value, 7);
  const stored = JSON.parse(await fs.readFile(path.join(f.directory, (await fs.readdir(f.directory))[0]), 'utf8'));
  assert.equal(stored.storedAt, 1_000_000);
  assert.equal(stored.data.value, 7);
});

test('query/page variants remain isolated and disk capacity stays bounded', async (t) => {
  const f = await fixture(t, { maxEntries: 2 });
  for (let page = 1; page <= 3; page++) {
    f.setFetch(() => response({ value: page }));
    assert.equal((await f.cache.get(`${url}?page=${page}`, validate, policy)).data.value, page);
  }
  assert.equal(f.calls(), 3);
  assert.equal((await fs.readdir(f.directory)).filter((file) => file.endsWith('.json')).length, 2);
});

test('private requests are refused before network access and clearing invalidates snapshots', async (t) => {
  const f = await fixture(t);
  await assert.rejects(f.cache.get(`${url}?includeHidden=true`, validate, policy));
  await assert.rejects(f.cache.get('https://fixture.example/api/v1/prompts', validate, policy));
  assert.equal(f.calls(), 0);
  await f.cache.get(url, validate, policy);
  await f.cache.clear();
  assert.equal((await fs.readdir(f.directory)).length, 0);
  await f.cache.get(url, validate, policy);
  assert.equal(f.calls(), 2);
});

test('in-flight responses cannot repopulate snapshots after editorial invalidation', async (t) => {
  const f = await fixture(t);
  let release;
  let started;
  const ready = new Promise((resolve) => { started = resolve; });
  f.setFetch(() => { started(); return new Promise((resolve) => { release = resolve; }); });
  const request = f.cache.get(url, validate, policy);
  await ready;
  await f.cache.clear();
  release(response({ value: 7 }));
  await request;
  assert.equal((await fs.readdir(f.directory).catch(() => [])).length, 0);
});

test('cold API failures produce an empty feed and an article error, never demo data or false 404', async (t) => {
  liveEnvironment(t);
  t.mock.method(global, 'fetch', async () => response({}, 503));
  const news = await getNews();
  assert.deepEqual(news.items, []);
  assert.equal(news.cacheStatus, 'unavailable');
  await assert.rejects(getArticle('real-slug'), (error) => error.status === 503);
});

test('article 404 stays missing and successful news fallback preserves page/limit parameters', async (t) => {
  liveEnvironment(t);
  const fetched = [];
  t.mock.method(global, 'fetch', async (address) => {
    fetched.push(new URL(address));
    if (address.includes('/articles/')) return response({}, 404);
    return response({ items: address.includes('aiOnly=true') ? [] : [newsItem], total: 1, page: 2 });
  });
  assert.equal((await getArticle('absent')).item, undefined);
  const news = await getNews(undefined, { aiOnly: true, fallbackToAll: true, limit: 5, page: 2 });
  assert.equal(news.items[0].id, 'real-news');
  assert.equal(news.page, 2);
  assert.ok(fetched.filter((address) => address.pathname.endsWith('/news')).every((address) => address.searchParams.get('page') === '2' && address.searchParams.get('limit') === '5'));
});

test('forecast outages have no demo fallback or false missing result', async (t) => {
  liveEnvironment(t);
  t.mock.method(global, 'fetch', async () => response({}, 503));
  assert.deepEqual(await getTodayForecasts(), []);
  await assert.rejects(getLiveForecast('missing'), (error) => error.status === 503);
});
