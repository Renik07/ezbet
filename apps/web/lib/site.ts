export const SITE_NAME = "ezbet.ru";
export const SITE_TITLE = "ezbet.ru - спортивные новости, аналитика и беттинг";
export const SITE_DESCRIPTION =
  "Свежие спортивные новости, материалы о футболе, хоккее, баскетболе, теннисе, киберспорте и беттинге.";

export function getSiteUrl() {
  const rawUrl =
    process.env.EZBET_PUBLIC_HOST ||
    process.env.NEXT_PUBLIC_SITE_URL ||
    "https://ezbet.ru";

  const withProtocol = rawUrl.startsWith("http://") || rawUrl.startsWith("https://") ? rawUrl : `https://${rawUrl}`;
  return withProtocol.replace(/\/+$/, "");
}

export function absoluteUrl(path = "/") {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getSiteUrl()}${normalizedPath}`;
}

export function truncateMeta(value: string, maxLength = 160) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
}
