"use server";

import { redirect } from "next/navigation";

import { clearAdminSession } from "@/lib/auth";

export async function logoutAdminNow() {
  await clearAdminSession();
  redirect("/login?notice=signed-out");
}
