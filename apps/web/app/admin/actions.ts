"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { resolveApiBaseUrl } from "@/lib/api";

function redirectWithError(notice: string, error: unknown) {
  const detail = extractApiErrorMessage(error);
  redirect(`/admin?notice=${notice}&detail=${encodeURIComponent(detail)}`);
}

async function apiPost(path: string, body: Record<string, unknown>) {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) {
    throw new Error("API base URL is not configured.");
  }

  const response = await fetch(new URL(path, baseUrl).toString(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body),
    cache: "no-store"
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response;
}

const PRECHECK_SOURCE_TYPES = new Set(["news_sitemap", "sitemap", "scraping"]);

function extractApiErrorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    try {
      const parsed = JSON.parse(error.message);
      if (typeof parsed?.detail === "string" && parsed.detail) {
        return parsed.detail;
      }
    } catch {}
    return error.message;
  }

  return "Не удалось сохранить источник.";
}

export async function savePromptVersion(formData: FormData) {
  try {
    await apiPost("/api/v1/prompts", {
      agent_key: String(formData.get("agentKey") ?? ""),
      name: String(formData.get("name") ?? ""),
      system_prompt: String(formData.get("systemPrompt") ?? ""),
      user_prompt_template: String(formData.get("userPromptTemplate") ?? ""),
      model: String(formData.get("model") ?? ""),
      notes: String(formData.get("notes") ?? ""),
      activate: formData.get("activate") === "on"
    });
  } catch (error) {
    redirectWithError("prompt-save-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  redirect("/admin?notice=prompt-saved");
}

export async function activatePromptVersion(formData: FormData) {
  const promptId = String(formData.get("promptId") ?? "");
  try {
    await apiPost(`/api/v1/prompts/${promptId}/status`, {
      status: "active"
    });
  } catch (error) {
    redirectWithError("prompt-activate-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  redirect("/admin?notice=prompt-activated");
}

export async function archivePromptVersion(formData: FormData) {
  const promptId = String(formData.get("promptId") ?? "");
  try {
    await apiPost(`/api/v1/prompts/${promptId}/status`, {
      status: "archived"
    });
  } catch (error) {
    redirectWithError("prompt-archive-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  redirect("/admin?notice=prompt-archived");
}

export async function runEditorialNow() {
  try {
    await apiPost("/api/v1/editorial/run?limit=10", {});
  } catch (error) {
    redirectWithError("editorial-run-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  revalidatePath("/news");
  revalidatePath("/");
  redirect("/admin?notice=editorial-run");
}

export async function runContentPlannerNow() {
  try {
    await apiPost("/api/v1/content-plan/run?limit=10", {});
  } catch (error) {
    redirectWithError("content-plan-run-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  redirect("/admin?notice=content-plan-run");
}

export async function resetDatabaseNow() {
  try {
    await apiPost("/api/v1/dev/reset", {});
  } catch (error) {
    redirectWithError("db-reset-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  revalidatePath("/news");
  revalidatePath("/");
  redirect("/admin?notice=db-reset");
}

export async function ingestRssTestBatchNow() {
  try {
    await apiPost("/api/v1/ingest/sources?limit=5&perSource=true", {});
  } catch (error) {
    redirectWithError("sources-ingest-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  revalidatePath("/news");
  revalidatePath("/");
  redirect("/admin?notice=sources-ingested");
}

export async function saveSchedulerSettingsNow(formData: FormData) {
  const enabled = String(formData.get("enabled") ?? "") === "on";
  const intervalMinutes = Number(formData.get("intervalMinutes") ?? 60);
  const batchSize = Number(formData.get("batchSize") ?? 5);
  const runEnrichment = String(formData.get("runEnrichment") ?? "") === "on";

  try {
    await apiPost("/api/v1/scheduler", {
      enabled,
      intervalMinutes,
      batchSize,
      runEnrichment
    });
  } catch (error) {
    redirectWithError("scheduler-save-error", error);
  }

  revalidatePath("/admin");
  redirect("/admin?notice=scheduler-saved");
}

export async function runSchedulerNow() {
  try {
    const response = await apiPost("/api/v1/scheduler/run", {});
    const payload = (await response.json()) as { ran?: boolean; reason?: string };
    if (!payload.ran) {
      throw new Error(`Scheduler не запустился: ${payload.reason ?? "unknown"}`);
    }
  } catch (error) {
    redirectWithError("scheduler-run-error", error);
  }

  revalidatePath("/admin");
  revalidatePath("/studio");
  revalidatePath("/news");
  revalidatePath("/");
  redirect("/admin?notice=scheduler-run");
}

export async function runEnrichmentNow() {
  try {
    const response = await apiPost("/api/v1/enrichment/run?limit=10", {});
    const payload = (await response.json()) as { processed?: number; enriched?: number };
    const detail = `Обработано ${payload.processed ?? 0}, реально обогащено ${payload.enriched ?? 0}.`;
    revalidatePath("/admin");
    revalidatePath("/studio");
    revalidatePath("/news");
    revalidatePath("/");
    redirect(`/admin?notice=enrichment-run&detail=${encodeURIComponent(detail)}`);
  } catch (error) {
    redirectWithError("enrichment-run-error", error);
  }
}

export async function createSourceNow(formData: FormData) {
  const requestedSourceType = String(formData.get("resolvedSourceType") ?? formData.get("sourceType") ?? "auto");
  const sourceKey = String(formData.get("key") ?? "");
  const title = String(formData.get("title") ?? "");
  const url = String(formData.get("url") ?? "");
  const category = String(formData.get("category") ?? "");
  const notes = String(formData.get("notes") ?? "");
  const probeOk = String(formData.get("probeOk") ?? "") === "true";
  const probedKey = String(formData.get("probedKey") ?? "");
  const probedUrl = String(formData.get("probedUrl") ?? "");
  const probedSourceType = String(formData.get("resolvedSourceType") ?? "");

  try {
    if (!probeOk) {
      throw new Error("Сначала выполните успешную проверку источника.");
    }
    if (sourceKey !== probedKey || url !== probedUrl || requestedSourceType !== probedSourceType) {
      throw new Error("После изменения key, URL или type сначала выполните проверку заново.");
    }
    const sourceType = requestedSourceType;
    if (!sourceType || sourceType === "auto") {
      throw new Error("Проверка не подтвердила подходящий тип источника. Сначала проверьте источник.");
    }
    const requiresPrecheck = PRECHECK_SOURCE_TYPES.has(sourceType);

    await apiPost("/api/v1/sources", {
      key: sourceKey,
      title,
      url,
      category,
      source_type: sourceType,
      status: requiresPrecheck ? "draft" : "active",
      notes
    });

    if (requiresPrecheck) {
      try {
        const probeResponse = await apiPost(`/api/v1/sources/${sourceKey}/probe`, {});
        const probeResult = await probeResponse.json();
        if (!probeResult.ok) {
          throw new Error("Preflight не подтвердил рабочий поток новостей.");
        }
        await apiPost(`/api/v1/sources/${sourceKey}`, {
          title,
          url,
          category,
          source_type: sourceType,
          status: "active",
          notes
        });
      } catch (error) {
        try {
          await apiPost(`/api/v1/sources/${sourceKey}/delete`, {});
        } catch {}
        throw error;
      }
    }
  } catch (error) {
    redirect(`/admin?notice=source-save-error&detail=${encodeURIComponent(extractApiErrorMessage(error))}`);
  }

  revalidatePath("/admin");
  redirect("/admin?notice=source-created");
}

export async function probeNewSourceNow(formData: FormData) {
  const sourceKey = String(formData.get("key") ?? "");
  const title = String(formData.get("title") ?? "");
  const url = String(formData.get("url") ?? "");
  const sourceType = String(formData.get("sourceType") ?? "auto");
  const notes = String(formData.get("notes") ?? "");
  const params = new URLSearchParams({
    sourceKey,
    sourceTitle: title,
    sourceUrl: url,
    sourceType,
    sourceNotes: notes
  });

  try {
    const response = await apiPost("/api/v1/source-probe", {
      key: sourceKey,
      title,
      url,
      category: String(formData.get("category") ?? ""),
      source_type: sourceType,
      status: "draft",
      notes
    });
    const result = await response.json();
    params.set("notice", "source-draft-probed");
    params.set("probeOk", String(Boolean(result.ok)));
    params.set("probeReadiness", String(result.readiness ?? "unknown"));
    params.set("supportsRss", String(Boolean(result.supportsRss)));
    params.set("supportsNewsSitemap", String(Boolean(result.supportsNewsSitemap)));
    params.set("supportsSitemap", String(Boolean(result.supportsSitemap)));
    params.set("supportsScraping", String(Boolean(result.supportsScraping)));
    if (result.resolvedSourceType) {
      params.set("resolvedSourceType", String(result.resolvedSourceType));
    }
    if (result.resolvedSourceUrl) {
      params.set("resolvedSourceUrl", String(result.resolvedSourceUrl));
    }
    params.set("probeCount", String(result.itemCount ?? 0));
    params.set("probeFullTextOk", String(Boolean(result.fullTextOk)));
    params.set("probeLeadOk", String(Boolean(result.leadOk)));
    params.set("probeTagsCount", String(result.tagsCount ?? 0));
    if (result.sampleTitle) {
      params.set("probeSampleTitle", String(result.sampleTitle));
    }
    if (result.sampleUrl) {
      params.set("probeSampleUrl", String(result.sampleUrl));
    }
    if (result.message) {
      params.set("detail", String(result.message));
    }
  } catch (error) {
    params.set("notice", "source-draft-probe-error");
    params.set("detail", extractApiErrorMessage(error));
  }

  redirect(`/admin?${params.toString()}`);
}

export async function updateSourceNow(formData: FormData) {
  const sourceKey = String(formData.get("sourceKey") ?? "");
  try {
    await apiPost(`/api/v1/sources/${sourceKey}`, {
      title: String(formData.get("title") ?? ""),
      url: String(formData.get("url") ?? ""),
      category: String(formData.get("category") ?? ""),
      source_type: String(formData.get("sourceType") ?? "rss"),
      status: String(formData.get("status") ?? "draft"),
      notes: String(formData.get("notes") ?? "")
    });
  } catch (error) {
    redirect(`/admin?notice=source-save-error&detail=${encodeURIComponent(extractApiErrorMessage(error))}`);
  }

  revalidatePath("/admin");
  redirect("/admin?notice=source-updated");
}

export async function deleteSourceNow(formData: FormData) {
  const sourceKey = String(formData.get("sourceKey") ?? "");
  try {
    await apiPost(`/api/v1/sources/${sourceKey}/delete`, {});
  } catch (error) {
    redirectWithError("source-delete-error", error);
  }

  revalidatePath("/admin");
  redirect("/admin?notice=source-deleted");
}

export async function probeSourceNow(formData: FormData) {
  const sourceKey = String(formData.get("sourceKey") ?? "");
  try {
    await apiPost(`/api/v1/sources/${sourceKey}/probe`, {});
  } catch (error) {
    redirectWithError("source-probe-error", error);
  }

  revalidatePath("/admin");
  redirect("/admin?notice=source-probed");
}
