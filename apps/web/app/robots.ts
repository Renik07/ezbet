import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/news", "/news/"],
        disallow: ["/admin", "/studio", "/login"]
      }
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: absoluteUrl("/")
  };
}
