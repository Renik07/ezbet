import { getSitemapPart, xmlEscape, xmlResponse } from "@/lib/sitemap";
import { absoluteUrl } from "@/lib/site";
export const dynamic = "force-dynamic";
export async function GET(_request: Request, { params }: { params: Promise<{ part: string }> }) {
  const { part } = await params;
  if (part !== "static.xml" && !/^(0|[1-9]\d{0,9})\.xml$/.test(part)) return new Response("Not found", { status: 404 });
  const id = Number(part.slice(0, -4));
  if (part !== "static.xml" && id > 2147483647) return new Response("Not found", { status: 404 });
  try {
    const entries = part === "static.xml" ? ["/", "/news"].map((path) => `<url><loc>${xmlEscape(absoluteUrl(path))}</loc></url>`) :
      (await getSitemapPart(id)).map((item) => `<url><loc>${xmlEscape(absoluteUrl(`/news/${encodeURIComponent(item.slug)}`))}</loc><lastmod>${xmlEscape(item.updatedAt)}</lastmod></url>`);
    return xmlResponse(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${entries.join("")}</urlset>`);
  } catch {
    return new Response("Sitemap temporarily unavailable", { status: 503, headers: { "Retry-After": "60" } });
  }
}
