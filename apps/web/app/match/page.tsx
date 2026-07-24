import { redirect } from "next/navigation";
import { getTodayForecasts } from "@/lib/forecasts";

export default async function MatchIndexPage() {
  const [forecast] = await getTodayForecasts();
  if (!forecast) {
    redirect("/");
  }
  redirect(`/match/${forecast.slug}`);
}
