"use server";

import { redirect } from "next/navigation";

import { createAdminSession, isAdminAuthConfigured, validateAdminCredentials } from "@/lib/auth";

export async function loginAdminNow(formData: FormData) {
  const nextPath = String(formData.get("next") ?? "/admin") || "/admin";
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!isAdminAuthConfigured()) {
    redirect(`/login?notice=${encodeURIComponent("auth-not-configured")}`);
  }

  const isValid = await validateAdminCredentials(username, password);
  if (!isValid) {
    redirect(`/login?notice=${encodeURIComponent("invalid-credentials")}&next=${encodeURIComponent(nextPath)}`);
  }

  await createAdminSession();
  redirect(nextPath.startsWith("/") ? nextPath : "/admin");
}
