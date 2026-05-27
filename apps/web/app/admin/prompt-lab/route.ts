import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";

import { resolveApiBaseUrl } from "@/lib/api";

function buildRedirect(request: Request, notice: string, detail?: string) {
  const url = new URL("/admin", request.url);
  url.searchParams.set("notice", notice);
  if (detail) {
    url.searchParams.set("detail", detail);
  }
  return NextResponse.redirect(url, { status: 303 });
}

function extractApiErrorMessage(payload: string) {
  try {
    const parsed = JSON.parse(payload);
    if (typeof parsed?.detail === "string" && parsed.detail) {
      return parsed.detail;
    }
  } catch {}
  return payload || "Не удалось выполнить TEMP prompt lab.";
}

export async function POST(request: Request) {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) {
    return buildRedirect(request, "prompt-lab-run-error", "API base URL is not configured.");
  }

  try {
    const response = await fetch(new URL("/api/v1/prompt-lab/run?limit=3", baseUrl).toString(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({}),
      cache: "no-store"
    });

    if (!response.ok) {
      const text = await response.text();
      return buildRedirect(request, "prompt-lab-run-error", extractApiErrorMessage(text));
    }

    const payload = (await response.json()) as {
      item?: { selectedCount?: number; freshCount?: number; reusedCount?: number };
    };

    const selected = payload.item?.selectedCount ?? 0;
    const fresh = payload.item?.freshCount ?? 0;
    const reused = payload.item?.reusedCount ?? 0;
    const detail = `Выбрано ${selected}, свежих ${fresh}, из пула ${reused}.`;

    revalidatePath("/admin");
    revalidatePath("/studio");

    return buildRedirect(request, "prompt-lab-run", detail);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Не удалось выполнить TEMP prompt lab.";
    return buildRedirect(request, "prompt-lab-run-error", detail);
  }
}
