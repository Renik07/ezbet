import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, readdir, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

export class PublicApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "PublicApiError";
  }
}

type Snapshot = { version: 1; key: string; storedAt: number; data: unknown };
type Policy = { freshMs: number; staleMs: number; timeoutMs?: number };
export type CachedResult<T> = { data: T; source: "api" | "cache" | "stale" };

// Only anonymous public responses belong here. Admin fetches use separate loaders.
export class PublicDataCache {
  private readonly memory = new Map<string, Snapshot>();
  private readonly pending = new Map<string, Promise<CachedResult<unknown>>>();
  private readonly failures = new Map<string, { until: number; error: PublicApiError }>();
  private generation = 0;
  private readonly maxBytes = 512 * 1024;

  constructor(private readonly options: {
    directory: string;
    maxEntries?: number;
    now?: () => number;
    fetcher?: typeof fetch;
  }) {}

  private now() { return this.options.now?.() ?? Date.now(); }
  private get maxEntries() { return this.options.maxEntries ?? 128; }
  private file(key: string) {
    return path.join(this.options.directory, `${createHash("sha256").update(key).digest("hex")}.json`);
  }

  private remember(snapshot: Snapshot) {
    this.memory.delete(snapshot.key);
    this.memory.set(snapshot.key, snapshot);
    while (this.memory.size > this.maxEntries) this.memory.delete(this.memory.keys().next().value!);
  }

  private async read<T>(key: string, validate: (data: unknown) => T): Promise<Snapshot | undefined> {
    const generation = this.generation;
    let snapshot = this.memory.get(key);
    if (!snapshot) {
      try {
        const file = this.file(key);
        if ((await stat(file)).size > this.maxBytes) return undefined;
        snapshot = JSON.parse(await readFile(file, "utf8")) as Snapshot;
      } catch { return undefined; }
    }
    if (snapshot?.version !== 1 || snapshot.key !== key || !Number.isFinite(snapshot.storedAt) || snapshot.storedAt > this.now()) return undefined;
    try { validate(snapshot.data); } catch { return undefined; }
    if (generation !== this.generation) return undefined;
    this.remember(snapshot);
    return snapshot;
  }

  private async write(snapshot: Snapshot, generation: number) {
    this.remember(snapshot);
    const file = this.file(snapshot.key);
    const temporary = `${file}.${randomUUID()}.tmp`;
    try {
      await mkdir(this.options.directory, { recursive: true });
      await writeFile(temporary, JSON.stringify(snapshot), { mode: 0o600 });
      if (generation !== this.generation) return;
      await rename(temporary, file);
      if (generation !== this.generation) { await unlink(file).catch(() => {}); return; }
      const files = await readdir(this.options.directory);
      if (files.length > this.maxEntries) {
        const entries = await Promise.all(files.filter((name) => name.endsWith(".json")).map(async (name) => {
          const filename = path.join(this.options.directory, name);
          return { filename, time: (await stat(filename).catch(() => ({ mtimeMs: Infinity }))).mtimeMs };
        }));
        entries.sort((a, b) => b.time - a.time);
        await Promise.all(entries.slice(this.maxEntries).map(({ filename }) => unlink(filename).catch(() => {})));
      }
    } catch {
      // Read-only/full disks must not turn a successful API response into an outage.
    } finally {
      await unlink(temporary).catch(() => {});
    }
  }

  private async invalidate(key: string) {
    this.memory.delete(key);
    await unlink(this.file(key)).catch(() => {});
  }

  async clear() {
    this.generation += 1;
    this.memory.clear();
    this.failures.clear();
    this.pending.clear();
    try {
      const files = await readdir(this.options.directory);
      await Promise.all(files.filter((name) => name.endsWith(".json")).map((name) =>
        unlink(path.join(this.options.directory, name)).catch(() => {})));
    } catch { /* No persisted snapshots yet. */ }
  }

  async get<T>(url: string, validate: (data: unknown) => T, policy: Policy): Promise<CachedResult<T>> {
    const address = new URL(url);
    if (address.username || address.password || address.searchParams.has("includeHidden") ||
        !/^\/api\/v1\/(sitemap(?:\/\d+)?|news|articles\/[^/]+|forecasts(?:\/[^/]+)?)$/.test(address.pathname)) {
      throw new PublicApiError("Only anonymous public API data may be cached.");
    }
    address.searchParams.sort();
    const key = address.toString();
    const snapshot = await this.read(key, validate);
    const age = snapshot ? this.now() - snapshot.storedAt : Infinity;
    if (snapshot && age < policy.freshMs) return { data: validate(snapshot.data), source: "cache" };
    const failure = this.failures.get(key);
    if (failure && failure.until > this.now()) {
      if (snapshot && age <= policy.staleMs && (!failure.error.status || failure.error.status >= 500)) {
        return { data: validate(snapshot.data), source: "stale" };
      }
      throw failure.error;
    }
    const active = this.pending.get(key);
    if (active) return active as Promise<CachedResult<T>>;
    const generation = this.generation;
    const load = async (): Promise<CachedResult<T>> => {
      try {
        const response = await (this.options.fetcher ?? fetch)(key, {
          cache: "no-store", signal: AbortSignal.timeout(policy.timeoutMs ?? 8000)
        });
        if (!response.ok) throw new PublicApiError(`Public API returned ${response.status}.`, response.status);
        if (Number(response.headers.get("content-length")) > this.maxBytes) throw new PublicApiError("Public API response is too large.");
        const body = await response.text();
        if (Buffer.byteLength(body) > this.maxBytes) throw new PublicApiError("Public API response is too large.");
        const data = validate(JSON.parse(body));
        if (generation === this.generation) await this.write({ version: 1, key, storedAt: this.now(), data }, generation);
        this.failures.delete(key);
        return { data, source: "api" };
      } catch (cause) {
        const error = cause instanceof PublicApiError ? cause : new PublicApiError("Public API is temporarily unavailable.");
        if (generation === this.generation) this.failures.set(key, { until: this.now() + 10_000, error });
        while (this.failures.size > this.maxEntries) this.failures.delete(this.failures.keys().next().value!);
        if (error.status && error.status < 500) await this.invalidate(key);
        // A failure never extends the storedAt timestamp or the stale deadline.
        if (generation === this.generation && snapshot && this.now() - snapshot.storedAt <= policy.staleMs && (!error.status || error.status >= 500)) {
          return { data: validate(snapshot.data), source: "stale" };
        }
        throw error;
      } finally { if (generation === this.generation) this.pending.delete(key); }
    };
    const request = load();
    this.pending.set(key, request as Promise<CachedResult<unknown>>);
    return request;
  }
}

export const publicDataCache = new PublicDataCache({
  directory: process.env.EZBET_PUBLIC_CACHE_DIR || path.join(process.cwd(), ".next/cache/public-data")
});
