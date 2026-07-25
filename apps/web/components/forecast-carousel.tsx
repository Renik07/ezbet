"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

export function ForecastCarousel({ children }: { children: ReactNode }) {
  const stripRef = useRef<HTMLDivElement>(null);
  const [canScrollBack, setCanScrollBack] = useState(false);
  const [canScrollForward, setCanScrollForward] = useState(false);

  const updateButtons = useCallback(() => {
    const strip = stripRef.current;
    if (!strip) return;
    setCanScrollBack(strip.scrollLeft > 2);
    setCanScrollForward(strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 2);
  }, []);

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    updateButtons();
    strip.addEventListener("scroll", updateButtons, { passive: true });
    const observer = new ResizeObserver(updateButtons);
    observer.observe(strip);
    return () => {
      strip.removeEventListener("scroll", updateButtons);
      observer.disconnect();
    };
  }, [updateButtons]);

  function scroll(direction: "back" | "forward") {
    const strip = stripRef.current;
    if (!strip) return;
    strip.scrollBy({ left: (direction === "forward" ? 1 : -1) * Math.max(320, strip.clientWidth * 0.8), behavior: "smooth" });
  }

  return (
    <div className="forecast-carousel">
      <div ref={stripRef} className="forecast-strip" aria-label="Прогнозы на ближайшие футбольные матчи">
        {children}
      </div>
      <button className="forecast-arrow forecast-arrow--back" type="button" aria-label="Предыдущие прогнозы" onClick={() => scroll("back")} disabled={!canScrollBack}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
      </button>
      <button className="forecast-arrow forecast-arrow--forward" type="button" aria-label="Следующие прогнозы" onClick={() => scroll("forward")} disabled={!canScrollForward}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 4.5 13 10l-5.5 5.5" /></svg>
      </button>
    </div>
  );
}
