"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { METRIKA_ID } from "@/lib/metrika";

declare global {
  interface Window {
    ym?: (...args: unknown[]) => void;
  }
}

export function YandexMetrikaPageViews() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const hasTrackedInitialPage = useRef(false);

  useEffect(() => {
    if (!hasTrackedInitialPage.current) {
      hasTrackedInitialPage.current = true;
      return;
    }

    const query = searchParams.toString();
    const url = query ? `${pathname}?${query}` : pathname;
    window.ym?.(METRIKA_ID, "hit", url, {
      referer: document.referrer
    });
  }, [pathname, searchParams]);

  return null;
}
