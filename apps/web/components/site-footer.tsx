import Link from "next/link";

const sportLinks = [
  ["Футбол", "/news?query=Футбол"],
  ["Хоккей", "/news?query=Хоккей"],
  ["Баскетбол", "/news?query=Баскетбол"],
  ["Теннис", "/news?query=Теннис"],
  ["Киберспорт", "/news?query=Киберспорт"],
  ["MMA", "/news?query=MMA"]
];

const materialLinks = [
  ["Новости", "/news"],
  ["Аналитика", "/news?query=Аналитика"],
  ["Прогнозы", "/news?query=Прогноз"],
  ["Букмекеры", "/news?query=Букмекер"],
  ["Карта сайта", "/sitemap.xml"]
];

const aboutLinks = [
  ["Главная", "/"],
  ["Все новости", "/news"],
  ["Футбол", "/news?query=Футбол"],
  ["Теннис", "/news?query=Теннис"],
  ["Хоккей", "/news?query=Хоккей"]
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner container-wide">
        <div className="site-footer-top">
          <div className="site-footer-brand">
            <Link href="/" className="logo" aria-label="ezbet.ru - главная">
              <span className="logo-ez">ezbet</span>
              <span className="logo-dot-ru">.ru</span>
            </Link>
            <p className="site-footer-tagline">
              Спортивные новости, аналитика
              <br />и обзоры букмекеров
            </p>
            <div className="age-warning" aria-label="Материалы для лиц старше 18 лет">
              18+
            </div>
          </div>

          <nav className="site-footer-nav" aria-label="Навигация футера">
            <FooterColumn title="Спорт" links={sportLinks} />
            <FooterColumn title="Материалы" links={materialLinks} />
            <FooterColumn title="О сайте" links={aboutLinks} />
          </nav>
        </div>

        <div className="site-footer-divider" />

        <div className="site-footer-bottom">
          <p className="site-footer-legal">
            © 2024-2026 ezbet.ru - спортивная медиаплатформа. Все материалы носят
            информационный характер и не являются призывом к участию в азартных играх.
          </p>
          <div className="site-footer-legal-links">
            <Link href="/news?query=Ответственная%20игра" className="site-footer-legal-link">
              Ответственная игра
            </Link>
            <Link href="/news?query=Букмекеры" className="site-footer-legal-link">
              Букмекеры
            </Link>
            <a href="/sitemap.xml" className="site-footer-legal-link">
              Карта сайта
            </a>
          </div>
          <p className="site-footer-gambling-warning">
            Материалы сайта предназначены для лиц старше 18 лет. Азартные игры могут
            вызывать зависимость. Играйте ответственно.
          </p>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: string[][] }) {
  return (
    <div className="site-footer-nav-col">
      <div className="site-footer-nav-title">{title}</div>
      {links.map(([label, href]) => (
        <a key={`${title}-${label}`} href={href} className="site-footer-nav-link">
          {label}
        </a>
      ))}
    </div>
  );
}
