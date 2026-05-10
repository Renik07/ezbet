import type { Metadata } from "next";
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
      <body>{children}</body>
    </html>
  );
}
