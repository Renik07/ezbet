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
  const previousUrl = useRef<string | null>(null);

  useEffect(() => {
    const query = searchParams.toString();
    const path = query ? `${pathname}?${query}` : pathname;
    const url = new URL(path, window.location.origin).href;
    const referer = previousUrl.current ?? document.referrer;
    let attempts = 0;

    const sendHit = () => {
      attempts += 1;

      if (window.ym) {
        window.ym(METRIKA_ID, "hit", url, {
          referer,
          title: document.title
        });
        previousUrl.current = url;
        return;
      }

      if (attempts < 20) {
        window.setTimeout(sendHit, 250);
      }
    };

    sendHit();
  }, [pathname, searchParams]);

  return null;
}
