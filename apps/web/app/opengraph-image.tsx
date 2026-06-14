import { ImageResponse } from "next/og";
import { SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

export const runtime = "edge";
export const alt = "ezbet.ru - спортивные новости, аналитика и беттинг";
export const size = {
  width: 1200,
  height: 630
};
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#f8fafc",
          color: "#111827",
          padding: "72px",
          fontFamily: "Arial, sans-serif"
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between"
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "22px"
            }}
          >
            <div
              style={{
                width: "116px",
                height: "116px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "28px",
                background: "#2563eb",
                color: "#ffffff",
                fontSize: "54px",
                fontWeight: 900,
                letterSpacing: "-2px"
              }}
            >
              EZ
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "8px"
              }}
            >
              <div
                style={{
                  fontSize: "64px",
                  fontWeight: 900,
                  letterSpacing: "-2px"
                }}
              >
                {SITE_NAME}
              </div>
              <div
                style={{
                  color: "#2563eb",
                  fontSize: "28px",
                  fontWeight: 800,
                  textTransform: "uppercase"
                }}
              >
                Sport news hub
              </div>
            </div>
          </div>
          <div
            style={{
              border: "2px solid #dbe4f0",
              borderRadius: "999px",
              color: "#334155",
              padding: "16px 24px",
              fontSize: "24px",
              fontWeight: 800
            }}
          >
            LIVE
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "24px"
          }}
        >
          <div
            style={{
              maxWidth: "960px",
              fontSize: "72px",
              fontWeight: 900,
              letterSpacing: "-3px",
              lineHeight: 1
            }}
          >
            Спортивные новости, статьи и аналитика
          </div>
          <div
            style={{
              maxWidth: "900px",
              color: "#475569",
              fontSize: "32px",
              lineHeight: 1.35
            }}
          >
            {SITE_DESCRIPTION}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: "16px",
            color: "#0f172a",
            fontSize: "26px",
            fontWeight: 800
          }}
        >
          <span>Футбол</span>
          <span style={{ color: "#94a3b8" }}>·</span>
          <span>Хоккей</span>
          <span style={{ color: "#94a3b8" }}>·</span>
          <span>Баскетбол</span>
          <span style={{ color: "#94a3b8" }}>·</span>
          <span>Теннис</span>
          <span style={{ color: "#94a3b8" }}>·</span>
          <span>Киберспорт</span>
        </div>
      </div>
    ),
    size
  );
}
