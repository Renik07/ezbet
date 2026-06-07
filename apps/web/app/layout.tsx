import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ezbet.ru",
  description: "Автоматизированное спортивное медиа про новости, аналитику и букмекеров."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>
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
      </body>
    </html>
  );
}
