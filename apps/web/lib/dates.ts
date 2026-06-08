export const MOSCOW_TIME_ZONE = "Europe/Moscow";

export function formatMoscowDateTime(value: string | Date, dateStyle: "short" | "medium" | "long" = "medium") {
  return new Date(value).toLocaleString("ru-RU", {
    dateStyle,
    timeStyle: "short",
    timeZone: MOSCOW_TIME_ZONE
  });
}

export function formatMoscowDate(value: string | Date, dateStyle: "short" | "medium" | "long" = "medium") {
  return new Date(value).toLocaleDateString("ru-RU", {
    dateStyle,
    timeZone: MOSCOW_TIME_ZONE
  });
}
