import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import { Suspense } from "react";
import { GoogleAnalyticsPageViews } from "@/components/google-analytics";
import { SiteFooter } from "@/components/site-footer";
import { YandexMetrikaPageViews } from "@/components/yandex-metrika";
import { METRIKA_ID } from "@/lib/metrika";
import { absoluteUrl, getSiteUrl, SITE_DESCRIPTION, SITE_NAME, SITE_OG_IMAGE, SITE_TITLE } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  applicationName: SITE_NAME,
  title: {
    default: SITE_TITLE,
    template: `%s | ${SITE_NAME}`
  },
  description: SITE_DESCRIPTION,
  alternates: {
    canonical: "/",
    types: {
      "application/rss+xml": absoluteUrl("/feed.xml")
    }
  },
  openGraph: {
    type: "website",
    locale: "ru_RU",
    url: "/",
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [
      {
        url: SITE_OG_IMAGE,
        width: 1200,
        height: 630,
        alt: SITE_TITLE
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [SITE_OG_IMAGE]
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1
    }
  },
  verification: {
    yandex: "2bf869d644fb108e"
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const googleAnalyticsId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();

  return (
    <html lang="ru">
      <body>
        {googleAnalyticsId ? (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${googleAnalyticsId}`}
              strategy="afterInteractive"
            />
            <Script id="google-analytics" strategy="afterInteractive">
              {`
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', '${googleAnalyticsId}', { send_page_view: false });
              `}
            </Script>
          </>
        ) : null}
        <Script id="yandex-metrika" strategy="afterInteractive">
          {`
            (function(m,e,t,r,i,k,a){
              m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
              m[i].l=1*new Date();
              for (var j = 0; j < document.scripts.length; j++) { if (document.scripts[j].src === r) { return; } }
              k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
            })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=${METRIKA_ID}', 'ym');

            ym(${METRIKA_ID}, 'init', {defer:true, clickmap:true, ecommerce:"dataLayer", accurateTrackBounce:true, trackLinks:true});
          `}
        </Script>
        <noscript
          dangerouslySetInnerHTML={{
            __html: `<div><img src="https://mc.yandex.ru/watch/${METRIKA_ID}" style="position:absolute; left:-9999px;" alt="" /></div>`
          }}
        />
        <Suspense fallback={null}>
          <YandexMetrikaPageViews />
          {googleAnalyticsId ? <GoogleAnalyticsPageViews measurementId={googleAnalyticsId} /> : null}
        </Suspense>
        <header className="site-header">
          <div className="site-header-inner container-wide">
            <Link href="/" className="logo" aria-label="ezbet.ru - главная">
              <span className="logo-ez">ezbet</span>
              <span className="logo-dot-ru">.ru</span>
            </Link>
            <nav className="nav-main" aria-label="Основная навигация">
              <Link href="/news?query=Футбол" className="nav-link nav-link--football">
                Футбол
              </Link>
              <Link href="/news?query=Хоккей" className="nav-link nav-link--hockey">
                Хоккей
              </Link>
              <Link href="/news?query=Баскетбол" className="nav-link nav-link--basketball">
                Баскетбол
              </Link>
              <Link href="/news?query=Теннис" className="nav-link nav-link--tennis">
                Теннис
              </Link>
              <Link href="/news?query=Киберспорт" className="nav-link nav-link--cyber">
                Киберспорт
              </Link>
              <Link href="/news" className="nav-link nav-link--special">
                Все новости
              </Link>
            </nav>
          </div>
        </header>
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
