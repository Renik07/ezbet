"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

type GoogleAnalyticsPageViewsProps = {
  measurementId: string;
};

export function GoogleAnalyticsPageViews({ measurementId }: GoogleAnalyticsPageViewsProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const previousUrl = useRef<string | null>(null);

  useEffect(() => {
    if (!measurementId || !window.gtag) {
      return;
    }

    const query = searchParams.toString();
    const path = query ? `${pathname}?${query}` : pathname;
    const url = new URL(path, window.location.origin).href;

    if (previousUrl.current === url) {
      return;
    }

    window.gtag("event", "page_view", {
      page_location: url,
      page_path: path,
      page_title: document.title
    });
    previousUrl.current = url;
  }, [measurementId, pathname, searchParams]);

  return null;
}
