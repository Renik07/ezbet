"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

type StudioDiagnosticsRefreshProps = {
  enabled: boolean;
  intervalMs?: number;
};

export function StudioDiagnosticsRefresh({
  enabled,
  intervalMs = 30000
}: StudioDiagnosticsRefreshProps) {
  const router = useRouter();

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      router.refresh();
    }, intervalMs);

    return () => window.clearInterval(intervalId);
  }, [enabled, intervalMs, router]);

  return null;
}
