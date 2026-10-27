"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowUpRight, CheckCircle2, Clock3, Globe2, Loader2, Play, RefreshCw, XCircle } from "lucide-react";
import { createAudit, createBatch, getAuditStatus, getCrawlURLs } from "@/lib/api";
import type { AuditStatusResponse, CrawlURL } from "@/types/api";

const activeStatuses = new Set(["pending", "queued", "collecting", "running", "waiting_for_access", "waiting_for_approval"]);

function normalizeInput(value: string) {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function statusStyle(status: string) {
  if (["completed", "fetched"].includes(status)) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (["failed", "cancelled"].includes(status)) return "text-red-700 bg-red-50 border-red-200";
  if (["fetching", "processing", "running"].includes(status)) return "text-blue-700 bg-blue-50 border-blue-200";
  return "text-slate-600 bg-slate-100 border-slate-200";
}

export function Dashboard() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [scope, setScope] = useState<"page" | "website" | "batch">("website");
  const [batchUrls, setBatchUrls] = useState("");
  const [audit, setAudit] = useState<AuditStatusResponse | null>(null);
  const [crawlUrls, setCrawlUrls] = useState<CrawlURL[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (auditId: string) => {
    const [status, urls] = await Promise.all([getAuditStatus(auditId), getCrawlURLs(auditId)]);
    setAudit(status);
    setCrawlUrls(urls);
  }, []);

  useEffect(() => {
    if (!audit || !activeStatuses.has(audit.status)) return;
    const timer = window.setInterval(() => {
      refresh(audit.id).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to refresh audit status."));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [audit, refresh]);

  const counts = useMemo(() => {
    const pages = crawlUrls.filter((item) => item.resource_type === "page");
    return {
      discovered: pages.length,
      queued: pages.filter((item) => ["pending", "discovered", "queued"].includes(item.status)).length,
      active: pages.filter((item) => ["fetching", "processing"].includes(item.status)).length,
      completed: pages.filter((item) => ["fetched", "completed"].includes(item.status)).length,
      failed: pages.filter((item) => ["failed", "skipped"].includes(item.status)).length,
      reports: pages.filter((item) => item.deeply_audited).length,
    };
  }, [crawlUrls]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const target = normalizeInput(url.trim());
    if (!target) {
      setError("Enter a valid HTTP or HTTPS URL.");
      return;
    }
    setLoading(true);
    try {
      if (scope === "batch") {
        const targets = batchUrls.split(/[\n,]+/).map((item) => normalizeInput(item.trim())).filter((item): item is string => Boolean(item));
        if (!targets.length) throw new Error("Add at least one URL for a batch audit.");
        const batch = await createBatch(targets, `batch-${Date.now()}`, false);
        router.push(`/batches/${encodeURIComponent(batch.id)}`);
        return;
      }
      const created = await createAudit(target, {
        audit_type: scope,
        mode: "agentic",
        max_crawl_pages: scope === "website" ? 20 : 1,
        max_crawl_depth: scope === "website" ? 3 : 0,
      });
      router.push(`/audits/${encodeURIComponent(created.id)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start the audit.");
    } finally {
      setLoading(false);
    }
  }

  async function loadExisting() {
    if (!audit) return;
    setRefreshing(true);
    try {
      await refresh(audit.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to refresh the audit.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/95">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight">
            <span className="grid size-9 place-items-center rounded-xl bg-indigo-500"><Globe2 size={19} /></span>
            SEO Audit Workspace
          </Link>
          <Link href="/batches" className="text-sm text-slate-400 hover:text-white">Saved batch audits</Link>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-5 py-8">
        <section className="rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-900/70 p-6 shadow-2xl lg:p-8">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-300">Audit any website</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">One workspace for crawling, analysis, and page reports.</h1>
            <p className="mt-3 text-sm leading-6 text-slate-400">Start a page audit, crawl a website, or submit multiple URLs. Live browser activity and saved AI findings remain available from the audit workspace.</p>
          </div>
          <form onSubmit={submit} className="mt-8 space-y-4">
            <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
              <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" className="h-12 rounded-xl border border-slate-700 bg-slate-950 px-4 text-sm outline-none ring-indigo-500 placeholder:text-slate-600 focus:ring-2" />
              <button disabled={loading} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-indigo-500 px-6 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-60">
                {loading ? <Loader2 size={17} className="animate-spin" /> : <Play size={17} />} Start audit
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {(["page", "website", "batch"] as const).map((value) => (
                <button type="button" key={value} onClick={() => setScope(value)} className={`rounded-lg border px-3 py-2 text-xs font-medium capitalize ${scope === value ? "border-indigo-400 bg-indigo-500/15 text-indigo-200" : "border-slate-700 text-slate-400 hover:text-white"}`}>
                  {value === "page" ? "Single page" : value === "website" ? "Website crawl" : "URL batch"}
                </button>
              ))}
            </div>
            {scope === "batch" && <textarea value={batchUrls} onChange={(event) => setBatchUrls(event.target.value)} rows={4} placeholder="Add one URL per line" className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />}
          </form>
          {error && <div role="alert" className="mt-4 flex gap-2 rounded-xl border border-red-900/70 bg-red-950/40 p-3 text-sm text-red-200"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}
        </section>

        {audit && (
          <section className="mt-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><p className="text-xs uppercase tracking-wider text-slate-500">Active audit</p><h2 className="mt-1 break-all text-lg font-semibold">{audit.url}</h2></div>
              <div className="flex items-center gap-2"><span className={`rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusStyle(audit.status)}`}>{statusLabel(audit.status)}</span><button onClick={loadExisting} disabled={refreshing} className="rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-white"><RefreshCw size={15} className={refreshing ? "animate-spin" : ""} /></button><Link href={`/audits/${audit.id}`} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900">Open workspace</Link></div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              {([["Discovered", counts.discovered, Globe2], ["Queued", counts.queued, Clock3], ["Active", counts.active, Loader2], ["Completed", counts.completed, CheckCircle2], ["Failed", counts.failed, XCircle], ["Reports", counts.reports, CheckCircle2]] as const).map(([label, value, Icon]) => <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-4"><Icon size={16} className="text-indigo-300" /><p className="mt-3 text-xs text-slate-500">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></div>)}
            </div>
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
              <div className="border-b border-slate-800 px-5 py-4"><h3 className="font-semibold">Crawl inventory</h3><p className="mt-1 text-xs text-slate-500">Deep reports are separate from discovered or shallowly checked pages.</p></div>
              <div className="divide-y divide-slate-800">
                {crawlUrls.filter((item) => item.resource_type === "page").map((item) => <div key={item.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1fr)_130px_130px_110px] md:items-center"><div className="min-w-0"><p className="truncate text-sm font-medium">{item.page_title || "Untitled page"}</p><p className="truncate text-xs text-slate-500">{item.url}</p></div><span className={`w-fit rounded-full border px-2 py-1 text-[11px] capitalize ${statusStyle(item.status)}`}>{statusLabel(item.status)}</span><span className={`w-fit rounded-full border px-2 py-1 text-[11px] ${item.deeply_audited ? "border-emerald-800 bg-emerald-950/40 text-emerald-300" : "border-slate-700 text-slate-500"}`}>{item.deeply_audited ? "Report available" : "Discovery only"}</span>{item.deeply_audited ? <Link target="_blank" href={`/audits/${audit.id}/pages/${item.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-300 hover:text-indigo-200">View report <ArrowUpRight size={13} /></Link> : <span className="text-xs text-slate-600">Not available</span>}</div>)}
                {!crawlUrls.some((item) => item.resource_type === "page") && <p className="px-5 py-10 text-center text-sm text-slate-500">No page records have arrived yet.</p>}
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
