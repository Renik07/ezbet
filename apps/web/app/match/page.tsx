import { redirect } from "next/navigation";
import { getTodayForecasts } from "@/lib/forecasts";

export default async function MatchIndexPage() {
  const [forecast] = await getTodayForecasts();
  redirect(`/match/${forecast.slug}`);
}
