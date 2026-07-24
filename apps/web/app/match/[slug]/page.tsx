import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getLiveForecast, getTodayForecasts } from "@/lib/forecasts";
import { absoluteUrl, SITE_NAME } from "@/lib/site";

export const dynamic = "force-dynamic";

function withoutTerminalPunctuation(value: string): string {
  return value.trim().replace(/[.!?;:,]+$/u, "");
}

function asSentence(value: string): string {
  return `${withoutTerminalPunctuation(value)}.`;
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const forecast = await getLiveForecast(slug);
  if (!forecast) return { title: "Прогноз не найден", robots: { index: false, follow: false } };

  const title = `${forecast.homeTeam} — ${forecast.awayTeam}: прогноз на матч`;
  return {
    title,
    description: forecast.lead,
    alternates: { canonical: `/match/${forecast.slug}` },
    openGraph: { title, description: forecast.lead, url: `/match/${forecast.slug}`, siteName: SITE_NAME },
  };
}

export default async function MatchForecastPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const forecast = await getLiveForecast(slug);
  if (!forecast) notFound();

  const moreForecasts = (await getTodayForecasts()).filter((item) => item.slug !== forecast.slug).slice(0, 3);
  const pageUrl = absoluteUrl(`/match/${forecast.slug}`);
  const title = `${forecast.homeTeam} — ${forecast.awayTeam}: прогноз на матч`;
  const cleanPick = withoutTerminalPunctuation(forecast.pick);

  return (
    <main className="match-detail-page container-wide">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
        "@context": "https://schema.org", "@type": "Article", headline: title, description: forecast.lead,
        url: pageUrl, inLanguage: "ru-RU", publisher: { "@type": "Organization", name: SITE_NAME }
      }) }} />
      <nav className="breadcrumb match-breadcrumb" aria-label="Навигация">
        <Link href="/" className="breadcrumb-link">Главная</Link>
        <span className="breadcrumb-sep">›</span>
        <span className="breadcrumb-current">{forecast.homeTeam} — {forecast.awayTeam}</span>
      </nav>

      <section className="match-detail-hero match-forecast-hero" aria-labelledby="match-title">
        <div className="match-detail-copy">
          <div className="tournament-kicker">Прогноз на матч · {forecast.league}</div>
          <h1 className="match-detail-title" id="match-title">{title}</h1>
          <p className="match-detail-lead">{forecast.lead}</p>
        </div>
        <div className="match-scoreboard">
          <div className="score-team"><span className="team-mark"><Image src={forecast.homeLogo} alt="" width={60} height={60} /></span><strong>{forecast.homeTeam}</strong></div>
          <div className="score-mid"><span>{forecast.kickoff}</span><strong>vs</strong></div>
          <div className="score-team"><span className="team-mark team-mark--blue"><Image src={forecast.awayLogo} alt="" width={60} height={60} /></span><strong>{forecast.awayTeam}</strong></div>
          <div className="match-hero-odds" aria-label="Коэффициенты на матч">
            <span className="match-odd"><b>П1</b>{forecast.odds.home}</span>
            <span className="match-odd"><b>X</b>{forecast.odds.draw}</span>
            <span className="match-odd is-selected"><b>П2</b>{forecast.odds.away}</span>
          </div>
        </div>
      </section>

      <div className="match-detail-grid">
        <article className="tournament-card match-article-card">
          <div className="tournament-card-header">
            <h2 className="tournament-card-title">Прогноз редакции</h2>
            <span className="tournament-card-note">форма команд и ключевые факторы</span>
          </div>
          <div className="match-article-content">
            <section className="analysis-block"><h3>Текущая форма {forecast.homeTeam}</h3><p>{forecast.homeForm}</p></section>
            <section className="analysis-block"><h3>Текущая форма {forecast.awayTeam}</h3><p>{forecast.awayForm}</p></section>
            <section className="analysis-block"><h3>Ключевые факторы</h3><ul className="analysis-list">{forecast.factors.map((factor) => <li key={factor}>{asSentence(factor)}</li>)}</ul></section>
            <section className="analysis-block"><h3>Вывод</h3><p>{forecast.lead} Поэтому наиболее аккуратным выбором выглядит сценарий: «{cleanPick}».</p></section>
            <div className="prediction-verdict"><span>Прогноз</span><strong>{asSentence(forecast.pick)}</strong></div>
          </div>
        </article>
        <aside className="match-detail-side">
          <div className="ad-slot ad-slot--sidebar" aria-label="Рекламный баннер">
            <span>Баннер 300×250</span>
          </div>
        </aside>
      </div>

      <section className="match-ad-wrap" aria-label="Рекламный баннер">
        <div className="ad-slot ad-slot--wide">
          <span>Баннер 970×250</span>
        </div>
      </section>

      <section className="match-carousel-section" aria-labelledby="more-forecasts-title">
        <div className="section-header"><h2 className="section-title" id="more-forecasts-title">Другие прогнозы</h2><Link href="/" className="section-link">Все прогнозы</Link></div>
        <div className="forecast-strip" aria-label="Другие прогнозы на матчи">
          {moreForecasts.map((item) => <article className="hero-article" key={item.slug}><div className="hero-forecast-copy"><div className="hero-title-row"><div className="hero-logo-pair" aria-hidden="true"><span className="hero-team-logo"><Image src={item.homeLogo} alt="" width={60} height={60} /></span><span className="hero-team-logo hero-team-logo--blue"><Image src={item.awayLogo} alt="" width={60} height={60} /></span></div><div className="hero-title-meta">{item.league} · {item.kickoff}</div><h3 className="hero-title">{item.homeTeam} — {item.awayTeam}</h3></div><div className="hero-pick"><Link href={`/match/${item.slug}`} className="hero-pick-btn">Читать прогноз</Link></div></div></article>)}
        </div>
      </section>
    </main>
  );
}
