export function resolveApiBaseUrl() {
  return (
    process.env.EZBET_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    (process.env.NODE_ENV === "development" ? "http://localhost:8000" : undefined)
  );
}
