import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import { Suspense } from "react";
import { SiteFooter } from "@/components/site-footer";
import { YandexMetrikaPageViews } from "@/components/yandex-metrika";
import { METRIKA_ID } from "@/lib/metrika";
import { getSiteUrl, SITE_DESCRIPTION, SITE_NAME, SITE_TITLE } from "@/lib/site";
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
    canonical: "/"
  },
  openGraph: {
    type: "website",
    locale: "ru_RU",
    url: "/",
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION
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
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>
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
