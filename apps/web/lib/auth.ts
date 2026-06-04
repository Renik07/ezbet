import { createHmac, timingSafeEqual } from "node:crypto";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const ADMIN_SESSION_COOKIE = "ezbet_admin_session";
const ADMIN_SESSION_TTL_SECONDS = 60 * 60 * 12;

type AdminAuthConfig = {
  username: string;
  password: string;
  sessionSecret: string;
};

type ParsedSession = {
  username: string;
  expiresAt: number;
  signature: string;
};

function isAdminSessionCookieSecure() {
  const override = process.env.EZBET_ADMIN_SECURE_COOKIE?.trim().toLowerCase();
  if (override === "false" || override === "0" || override === "no") {
    return false;
  }
  if (override === "true" || override === "1" || override === "yes") {
    return true;
  }
  return process.env.NODE_ENV === "production";
}

function getAdminAuthConfig(): AdminAuthConfig | null {
  const username = process.env.EZBET_ADMIN_USERNAME?.trim();
  const password = process.env.EZBET_ADMIN_PASSWORD?.trim();
  const sessionSecret = (process.env.EZBET_ADMIN_SESSION_SECRET || password || "").trim();

  if (!username || !password || !sessionSecret) {
    return null;
  }

  return {
    username,
    password,
    sessionSecret
  };
}

function createSignature(username: string, expiresAt: number, sessionSecret: string) {
  return createHmac("sha256", sessionSecret).update(`${username}:${expiresAt}`).digest("hex");
}

function safeEqual(left: string, right: string) {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);

  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }

  return timingSafeEqual(leftBuffer, rightBuffer);
}

function encodeSession(session: ParsedSession) {
  return Buffer.from(JSON.stringify(session), "utf8").toString("base64url");
}

function decodeSession(value: string): ParsedSession | null {
  try {
    const parsed = JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as ParsedSession;
    if (
      typeof parsed?.username !== "string" ||
      typeof parsed?.expiresAt !== "number" ||
      typeof parsed?.signature !== "string"
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function isAdminAuthConfigured() {
  return getAdminAuthConfig() !== null;
}

export async function isAdminAuthenticated() {
  const config = getAdminAuthConfig();
  if (!config) {
    return false;
  }

  const cookieStore = await cookies();
  const sessionValues = cookieStore.getAll(ADMIN_SESSION_COOKIE).map((cookie) => cookie.value);
  if (!sessionValues.length) {
    return false;
  }

  return sessionValues.some((sessionValue) => {
    const parsed = decodeSession(sessionValue);
    if (!parsed) {
      return false;
    }

    if (parsed.username !== config.username || parsed.expiresAt <= Date.now()) {
      return false;
    }

    const expectedSignature = createSignature(parsed.username, parsed.expiresAt, config.sessionSecret);
    return safeEqual(parsed.signature, expectedSignature);
  });
}

export async function requireAdminSession(nextPath = "/admin") {
  if (await isAdminAuthenticated()) {
    return;
  }

  redirect(`/login?next=${encodeURIComponent(nextPath)}`);
}

export async function createAdminSession() {
  const config = getAdminAuthConfig();
  if (!config) {
    throw new Error("Admin auth is not configured.");
  }

  const cookieStore = await cookies();
  const expiresAt = Date.now() + ADMIN_SESSION_TTL_SECONDS * 1000;
  const signature = createSignature(config.username, expiresAt, config.sessionSecret);

  cookieStore.set(ADMIN_SESSION_COOKIE, encodeSession({ username: config.username, expiresAt, signature }), {
    httpOnly: true,
    secure: isAdminSessionCookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge: ADMIN_SESSION_TTL_SECONDS
  });
}

export async function clearAdminSession() {
  const cookieStore = await cookies();
  cookieStore.set(ADMIN_SESSION_COOKIE, "", {
    httpOnly: true,
    secure: isAdminSessionCookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge: 0
  });
}

export async function validateAdminCredentials(username: string, password: string) {
  const config = getAdminAuthConfig();
  if (!config) {
    return false;
  }

  return safeEqual(username, config.username) && safeEqual(password, config.password);
}
