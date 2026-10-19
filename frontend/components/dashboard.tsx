"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowUpRight, CircleHelp, Globe2, Loader2, RefreshCw, Search, Sparkles } from "lucide-react";

import { createAudit, getAuditStatus, getCrawlURLs } from "@/lib/api";
import type { AuditStatusResponse, CrawlStatus, CrawlURL } from "@/types/api";

import { StatusBadge } from "./status-badge";

const terminalStatuses = new Set(["collected", "completed", "failed"]);
const crawlFilters: Array<{ value: CrawlStatus | "all"; label: string }> = [
  { value: "all", label: "All URLs" },
  { value: "pending", label: "Pending" },
  { value: "fetching", label: "Fetching" },
  { value: "fetched", label: "Fetched" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function validateURL(value: string) {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

export function Dashboard() {
  const [input, setInput] = useState("");
  const [audit, setAudit] = useState<AuditStatusResponse | null>(null);
  const [urls, setUrls] = useState<CrawlURL[]>([]);
  const [filter, setFilter] = useState<CrawlStatus | "all">("all");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const refresh = useCallback(async (auditId: string) => {
    const [status, inventory] = await Promise.all([
      getAuditStatus(auditId),
      getCrawlURLs(auditId),
    ]);
    setAudit(status);
    setUrls(inventory);
    return status;
  }, []);

  useEffect(() => {
    if (!audit || terminalStatuses.has(audit.status)) return;
    const timer = window.setInterval(async () => {
      try {
        await refresh(audit.id);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Unable to refresh audit progress.");
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [audit, refresh]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = validateURL(input.trim());
    if (!normalized) {
      setValidationError("Enter a valid HTTP or HTTPS website URL.");
      return;
    }
    setValidationError(null);
    setError(null);
    setLoading(true);
    try {
      const created = await createAudit(normalized);
      await refresh(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start the audit.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh() {
    if (!audit) return;
    setRefreshing(true);
    setError(null);
    try {
      await refresh(audit.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to refresh audit progress.");
    } finally {
      setRefreshing(false);
    }
  }

  const visibleURLs = useMemo(
    () => (filter === "all" ? urls : urls.filter((item) => item.status === filter)),
    [filter, urls],
  );
  const fetchedCount = urls.filter((item) => item.status === "fetched").length;
  const failedCount = urls.filter((item) => item.status === "failed").length;
  const mediaCount = urls.filter((item) => item.resource_type === "media").length;

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-950">
      <aside className="fixed inset-y-0 hidden w-64 border-r border-slate-200 bg-white px-5 py-7 lg:block">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <Sparkles size={18} />
          </div>
          <div>
            <p className="text-sm font-bold tracking-tight">RankPilot</p>
            <p className="text-xs text-slate-500">SEO intelligence</p>
          </div>
        </div>
        <nav className="mt-12 space-y-1 text-sm">
          <a className="flex items-center gap-3 rounded-lg bg-indigo-50 px-3 py-2.5 font-semibold text-indigo-700" href="#dashboard">
            <Globe2 size={17} /> Dashboard
          </a>
          <a className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-500 hover:bg-slate-50" href="#audits">
            <Search size={17} /> Audits
          </a>
          <a className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-500 hover:bg-slate-50" href="#urls">
            <ArrowUpRight size={17} /> Discovered URLs
          </a>
        </nav>
        <div className="absolute bottom-7 left-5 right-5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-500">
          <div className="mb-1 flex items-center gap-2 font-semibold text-slate-700"><CircleHelp size={14} /> Discovery first</div>
          SEO page analysis is not available for discovered pages yet.
        </div>
      </aside>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:px-10">
          <header id="dashboard" className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-indigo-600">Domain workspace</p>
              <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">SEO crawl dashboard</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Discover your site structure, monitor crawl progress, and identify what is ready for deeper SEO analysis.</p>
            </div>
            {audit && <button onClick={handleRefresh} disabled={refreshing} className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> Refresh</button>}
          </header>

          <section id="audits" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="mb-5 flex items-start gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600"><Globe2 size={19} /></div>
              <div><h2 className="font-semibold text-slate-900">Start a domain audit</h2><p className="mt-1 text-sm text-slate-500">Enter a URL to begin bounded sitemap and internal-link discovery.</p></div>
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
              <label className="sr-only" htmlFor="audit-url">Website URL</label>
              <input id="audit-url" value={input} onChange={(event) => setInput(event.target.value)} placeholder="https://example.com" disabled={loading} className="h-12 min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-4 text-sm outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100 disabled:opacity-60" />
              <button type="submit" disabled={loading} className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-6 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60">{loading && <Loader2 size={17} className="animate-spin" />} {loading ? "Starting…" : "Start audit"}</button>
            </form>
            {validationError && <p className="mt-3 text-sm text-red-600">{validationError}</p>}
            {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}
          </section>

          {audit ? (
            <>
              <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <Metric label="URLs discovered" value={urls.length.toString()} detail="Persistent crawl inventory" />
                <Metric label="Pages fetched" value={fetchedCount.toString()} detail="Successful 2xx HTML fetches" />
                <Metric label="Pages with SEO analysis" value="Unavailable" detail="Analysis is not exposed per discovered page" muted />
                <Metric label="Failed pages" value={failedCount.toString()} detail="Fetch or HTTP errors" />
                <Metric label="Media resources" value={mediaCount.toString()} detail="Excluded from HTML analysis" />
              </section>

              <section className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                  <div><div className="flex flex-wrap items-center gap-3"><h2 className="font-semibold text-slate-900">Audit progress</h2><StatusBadge status={audit.status} /></div><p className="mt-2 text-sm text-slate-500">{audit.url} · {audit.current_stage || "Waiting for collection"}</p></div>
                  <div className="text-left text-xs text-slate-400 sm:text-right">Started {formatDate(audit.created_at)}<br />Audit ID <span className="font-mono">{audit.id.slice(0, 8)}…</span></div>
                </div>
                <div className="grid gap-3 p-5 sm:grid-cols-3 sm:p-6">
                  <ProgressItem label="URL discovery" value={audit.status === "pending" ? "Queued" : "Active"} active={!terminalStatuses.has(audit.status)} />
                  <ProgressItem label="Page fetches" value={`${fetchedCount} of ${urls.length || "—"}`} active={fetchedCount < urls.length} />
                  <ProgressItem label="SEO analysis" value="Not available" active={false} />
                </div>
              </section>

              <section id="urls" className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
                  <div><h2 className="font-semibold text-slate-900">Discovered URLs</h2><p className="mt-1 text-sm text-slate-500">Pages are shown separately from SEO analysis results.</p></div>
                  <label className="sr-only" htmlFor="status-filter">Filter URLs by status</label>
                  <select id="status-filter" value={filter} onChange={(event) => setFilter(event.target.value as CrawlStatus | "all")} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-500">{crawlFilters.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
                </div>
                {visibleURLs.length === 0 ? <div className="p-10 text-center text-sm text-slate-500">{urls.length === 0 ? "No URLs have been persisted yet. Discovery may still be starting." : "No URLs match this filter."}</div> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-6 py-3 font-semibold">URL</th><th className="px-4 py-3 font-semibold">Status</th><th className="px-4 py-3 font-semibold">Type</th><th className="px-4 py-3 font-semibold">Depth</th><th className="px-4 py-3 font-semibold">HTTP</th><th className="px-4 py-3 font-semibold">Source</th><th className="px-6 py-3 font-semibold">Updated</th></tr></thead>                <tbody className="divide-y divide-slate-100">{visibleURLs.map((item) => <tr key={item.id} className="align-top hover:bg-slate-50/70"><td className="max-w-[320px] break-all px-6 py-4 font-medium text-slate-800">{item.url}{item.error && <p className="mt-1 text-xs font-normal text-slate-500">{item.error}</p>}</td><td className="px-4 py-4"><StatusBadge status={item.status} /></td><td className="px-4 py-4 text-slate-600">{item.resource_type === "media" ? "Media" : "Page"}</td><td className="px-4 py-4 text-slate-600">{item.depth}</td><td className="px-4 py-4 text-slate-600">{item.response_status ?? "—"}</td><td className="px-4 py-4 capitalize text-slate-600">{item.discovery_source.replace("_", " ")}</td><td className="whitespace-nowrap px-6 py-4 text-xs text-slate-500">{formatDate(item.updated_at)}</td></tr>)}</tbody></table></div>}
              </section>
            </>
          ) : (
            <section className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white/70 p-12 text-center"><div className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500"><Search size={21} /></div><h2 className="mt-4 font-semibold text-slate-800">No audit selected</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">Start an audit above to see real crawl states, URL depth, response codes, and discovery sources.</p></section>
          )}
        </div>
      </main>
    </div>
  );
}

function Metric({ label, value, detail, muted = false }: { label: string; value: string; detail: string; muted?: boolean }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm text-slate-500">{label}</p><p className={`mt-3 text-2xl font-bold tracking-tight ${muted ? "text-slate-400 text-lg" : "text-slate-950"}`}>{value}</p><p className="mt-1 text-xs text-slate-400">{detail}</p></div>;
}

function ProgressItem({ label, value, active }: { label: string; value: string; active: boolean }) {
  return <div className="rounded-xl bg-slate-50 p-4"><div className="flex items-center justify-between gap-2"><p className="text-sm font-medium text-slate-700">{label}</p><span className={`size-2 rounded-full ${active ? "bg-blue-500" : "bg-emerald-500"}`} /></div><p className="mt-2 text-xs text-slate-500">{value}</p></div>;
}
