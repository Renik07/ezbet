import { resolveApiBaseUrl } from "./api";
import { publicDataCache, PublicApiError } from "./public-data-cache";

export type SitemapEntry = { slug: string; updatedAt: string };
export type SitemapPart = { id: number; updatedAt: string };
const policy = { freshMs: 60_000, staleMs: 15 * 60_000 };

async function load<T>(path: string, validate: (value: unknown) => T): Promise<T> {
  const base = resolveApiBaseUrl();
  if (!base) throw new PublicApiError("Public API is not configured.");
  return (await publicDataCache.get(new URL(path, base).toString(), (value) => ({ items: validate(value) }), policy)).data.items;
}
function items(value: unknown): Record<string, unknown>[] {
  if (!value || typeof value !== "object" || !Array.isArray((value as { items?: unknown }).items)) {
    throw new PublicApiError("Invalid sitemap data.");
  }
  return (value as { items: Record<string, unknown>[] }).items;
}
function date(value: unknown): string {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) throw new PublicApiError("Invalid sitemap date.");
  return value;
}
export function getSitemapIndex(): Promise<SitemapPart[]> {
  return load("/api/v1/sitemap", (value) => items(value).map((item) => {
    if (!Number.isSafeInteger(item.id) || Number(item.id) < 0) throw new PublicApiError("Invalid sitemap range.");
    return { id: Number(item.id), updatedAt: date(item.updatedAt) };
  }));
}
export function getSitemapPart(part: number): Promise<SitemapEntry[]> {
  return load(`/api/v1/sitemap/${part}`, (value) => {
    const rows = items(value);
    if (rows.length > 1000) throw new PublicApiError("Sitemap range is too large.");
    return rows.map((item) => {
      if (typeof item.slug !== "string" || !item.slug) throw new PublicApiError("Invalid sitemap URL.");
      return { slug: item.slug, updatedAt: date(item.updatedAt) };
    });
  });
}
export function xmlEscape(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}
export function xmlResponse(xml: string): Response {
  if (Buffer.byteLength(xml, "utf8") > 50 * 1024 * 1024) throw new Error("Sitemap exceeds the protocol size limit.");
  return new Response(xml, { headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=60" } });
}
