import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PendingSubmitButton } from "@/components/pending-submit-button";
import { isAdminAuthConfigured, isAdminAuthenticated } from "@/lib/auth";

import { loginAdminNow } from "./actions";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = {
  title: "Вход",
  robots: {
    index: false,
    follow: false
  }
};

type LoginSearchParams = {
  notice?: string;
  next?: string;
};

function getLoginNotice(notice?: string) {
  switch (notice) {
    case "invalid-credentials":
      return "Неверный логин или пароль.";
    case "signed-out":
      return "Сессия завершена.";
    case "auth-not-configured":
      return "Авторизация админа еще не настроена через env.";
    default:
      return null;
  }
}

export default async function LoginPage({
  searchParams
}: {
  searchParams?: Promise<LoginSearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const nextRoute = params.next?.startsWith("/studio") ? "/studio" : "/admin";

  if (await isAdminAuthenticated()) {
    redirect(nextRoute);
  }

  const notice = getLoginNotice(params.notice);
  const authConfigured = isAdminAuthConfigured();

  return (
    <main className="page-shell" style={{ minHeight: "100vh", display: "grid", alignItems: "center" }}>
      <section className="hero" style={{ maxWidth: 560, margin: "0 auto", width: "100%" }}>
        <div className="eyebrow">Вход редактора</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Вход в админку ezbet</h1>
        <p>Одна общая сессия открывает доступ и к `/admin`, и к `/studio`.</p>
        {notice ? <p className="source-card-error">{notice}</p> : null}
        {!authConfigured ? (
          <p className="source-card-error">
            Для входа задайте `EZBET_ADMIN_USERNAME`, `EZBET_ADMIN_PASSWORD` и желательно `EZBET_ADMIN_SESSION_SECRET`.
          </p>
        ) : null}
        <form className="prompt-form" action={loginAdminNow} style={{ marginTop: 24 }}>
          <input type="hidden" name="next" value={nextRoute} />
          <label className="field">
            <span>Логин</span>
            <input name="username" autoComplete="username" required />
          </label>
          <label className="field">
            <span>Пароль</span>
            <input name="password" type="password" autoComplete="current-password" required />
          </label>
          <div className="hero-actions">
            <PendingSubmitButton
              className="button-primary"
              idleLabel="Войти"
              pendingLabel="Входим..."
              disabled={!authConfigured}
            />
          </div>
        </form>
      </section>
    </main>
  );
}
