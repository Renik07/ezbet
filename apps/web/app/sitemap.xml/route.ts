import { getSitemapIndex, xmlEscape, xmlResponse } from "@/lib/sitemap";
import { absoluteUrl } from "@/lib/site";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const parts = await getSitemapIndex();
    const entries = [`<sitemap><loc>${xmlEscape(absoluteUrl("/sitemaps/static.xml"))}</loc></sitemap>`,
      ...parts.map((part) => `<sitemap><loc>${xmlEscape(absoluteUrl(`/sitemaps/${part.id}.xml`))}</loc><lastmod>${xmlEscape(part.updatedAt)}</lastmod></sitemap>`)];
    return xmlResponse(`<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${entries.join("")}</sitemapindex>`);
  } catch {
    return new Response("Sitemap temporarily unavailable", { status: 503, headers: { "Retry-After": "60" } });
  }
}
