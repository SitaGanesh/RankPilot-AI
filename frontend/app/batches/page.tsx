"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  Loader2,
  PlusCircle,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";

import { createAudit, createBatch, getCrawlURLs, listBatches } from "@/lib/api";
import { IB_TUTORING_SEED_URLS } from "@/lib/constants";
import type { AuditBatch } from "@/types/api";

function statusClass(status: string) {
  if (status === "completed") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "failed") return "bg-red-50 text-red-700 border-red-200";
  if (status === "partial") return "bg-amber-50 text-amber-700 border-amber-200";
  if (status === "running") return "bg-blue-50 text-blue-700 border-blue-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function BatchesIndexPage() {
  const router = useRouter();
  const [batches, setBatches] = useState<AuditBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [urlsInput, setUrlsInput] = useState("");
  const [allowDiscovery, setAllowDiscovery] = useState(false);
  const [jumpId, setJumpId] = useState("");
  const [crawlDomainInput, setCrawlDomainInput] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoveryStatus, setDiscoveryStatus] = useState<string | null>(null);

  const fetchBatches = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listBatches();
      setBatches(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batches");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBatches();
  }, []);

  const handleLoadSeeds = () => {
    setUrlsInput(IB_TUTORING_SEED_URLS.join("\n"));
  };

  const handleClear = () => {
    setUrlsInput("");
  };

  const handleDiscoverLinks = async () => {
    const raw = crawlDomainInput.trim();
    if (!raw) return;
    setDiscovering(true);
    setDiscoveryStatus("Dispatching crawl to fetch page and parse HTML links…");
    try {
      const created = await createAudit(raw);
      setDiscoveryStatus("Crawler active — parsing internal HTML anchor links…");
      let discoveredUrls: string[] = [];
      for (let i = 0; i < 5; i++) {
        await new Promise((r) => setTimeout(r, 1200));
        const list = await getCrawlURLs(created.id);
        const pages = list.filter((item) => item.resource_type === "page").map((item) => item.url);
        if (pages.length > 0) {
          discoveredUrls = pages;
          if (discoveredUrls.length >= 5) break;
        }
      }
      if (discoveredUrls.length > 0) {
        setUrlsInput(discoveredUrls.join("\n"));
        setDiscoveryStatus(`Extracted ${discoveredUrls.length} HTML links from parser! URLs populated below.`);
      } else {
        setUrlsInput(raw);
        setDiscoveryStatus("Seed page registered. Target populated below.");
      }
    } catch (err) {
      setDiscoveryStatus(err instanceof Error ? err.message : "Failed to discover links from URL.");
    } finally {
      setDiscovering(false);
    }
  };

  const handleCreateBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    const rawUrls = urlsInput
      .split(/[\n,]+/)
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    if (rawUrls.length === 0) {
      setError("Please provide at least one valid URL to audit.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const idempotencyKey = "batch-" + Date.now() + "-" + Math.random().toString(36).substring(2, 8);
      const newBatch = await createBatch(rawUrls, idempotencyKey, allowDiscovery);
      router.push(`/batches/${encodeURIComponent(newBatch.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create batch audit.");
      setSubmitting(false);
    }
  };

  const handleJump = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = jumpId.trim();
    if (cleaned) {
      router.push(`/batches/${encodeURIComponent(cleaned)}`);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900">
      {/* Top Navigation */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3.5 sm:px-6">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2 text-slate-900 transition hover:text-indigo-600">
              <div className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-white shadow-sm">
                <Sparkles size={16} />
              </div>
              <span className="font-bold tracking-tight">RankPilot</span>
            </Link>
            <span className="text-slate-300">/</span>
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              <Layers size={16} className="text-indigo-600" />
              <span>Batch Audits</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
            >
              Single Domain Crawl
            </Link>
            <button
              onClick={fetchBatches}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {error && (
          <div className="mb-6 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-600" />
            <div>
              <p className="font-semibold">Batch Audit Error</p>
              <p className="mt-0.5 text-red-700">{error}</p>
            </div>
          </div>
        )}

        <div className="grid gap-8 lg:grid-cols-12">
          {/* Left Column: Create New Batch Form */}
          <section className="lg:col-span-7">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-2 text-indigo-600">
                <PlusCircle size={20} />
                <h2 className="text-lg font-bold text-slate-900">Create New Batch Audit</h2>
              </div>
              <p className="mt-1 text-sm text-slate-500">
                Queue multiple URLs for automated crawling and full 4-agent SEO analysis (On-page, Technical,
                IB-Content/CRO, Visibility).
              </p>

              <form onSubmit={handleCreateBatch} className="mt-6 space-y-5">
                {/* HTML Parser Link Discovery Box */}
                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-indigo-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-900">
                      Option 1: Extract Links from HTML Page First
                    </h3>
                  </div>
                  <p className="mt-1 text-xs text-indigo-950/70">
                    Enter a domain or landing page to crawl and extract all internal HTML navigation links automatically.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <input
                      type="text"
                      placeholder="https://tutors.tychr.com"
                      value={crawlDomainInput}
                      onChange={(e) => setCrawlDomainInput(e.target.value)}
                      disabled={discovering || submitting}
                      className="h-9 min-w-0 flex-1 rounded-lg border border-indigo-200 bg-white px-3 text-xs outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                    />
                    <button
                      type="button"
                      onClick={handleDiscoverLinks}
                      disabled={discovering || submitting || !crawlDomainInput.trim()}
                      className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 text-xs font-semibold text-white shadow-2xs hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {discovering ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                      {discovering ? "Parsing HTML Links…" : "Extract Links"}
                    </button>
                  </div>
                  {discoveryStatus && (
                    <p className="mt-2 text-xs font-medium text-indigo-700">{discoveryStatus}</p>
                  )}
                </div>

                <div>
                  <div className="flex items-center justify-between pb-1.5">
                    <label htmlFor="batch-urls" className="text-xs font-bold uppercase tracking-wider text-slate-500">
                      Option 2: Target URLs to Audit (One per line)
                    </label>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleLoadSeeds}
                        className="rounded bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100"
                      >
                        ⚡ Load 25 IB Tutoring URLs
                      </button>
                      <button
                        type="button"
                        onClick={handleClear}
                        className="text-xs text-slate-400 hover:text-slate-600"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                  <textarea
                    id="batch-urls"
                    rows={8}
                    value={urlsInput}
                    onChange={(e) => setUrlsInput(e.target.value)}
                    placeholder="https://tutors.tychr.com/ib-tutor/cities/singapore&#10;https://tutors.tychr.com/ib-tutor/cities/toronto&#10;https://tutors.tychr.com/ib-tutor/cities/london"
                    disabled={submitting}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-800 outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100 disabled:opacity-60"
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    {urlsInput.split(/[\n,]+/).filter((u) => u.trim().length > 0).length} URL(s) detected
                  </p>
                </div>

                <div className="flex items-center gap-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    id="allow-discovery"
                    checked={allowDiscovery}
                    onChange={(e) => setAllowDiscovery(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label htmlFor="allow-discovery" className="cursor-pointer text-xs font-medium text-slate-700">
                    Allow internal link discovery (discover and enqueue links found on seed pages)
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Creating Batch Audit…
                    </>
                  ) : (
                    <>
                      Start Batch Audit
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Jump to Batch Quick-Form */}
            <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-bold text-slate-900">Direct Batch Access</h3>
              <p className="mt-1 text-xs text-slate-500">Have a specific Batch ID? Jump straight to its dashboard.</p>
              <form onSubmit={handleJump} className="mt-4 flex gap-2">
                <input
                  type="text"
                  value={jumpId}
                  onChange={(e) => setJumpId(e.target.value)}
                  placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
                  className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 font-mono text-xs text-slate-800 outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                />
                <button
                  type="submit"
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-100 px-4 text-xs font-semibold text-slate-700 hover:bg-slate-200"
                >
                  <Search size={14} /> Open
                </button>
              </form>
            </div>
          </section>

          {/* Right Column: Recent Batches */}
          <section className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between pb-3">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500">Recent Batches</h2>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  {batches.length}
                </span>
              </div>

              {loading && batches.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-sm text-slate-400">
                  <Loader2 size={18} className="mr-2 animate-spin text-indigo-600" />
                  Loading batches…
                </div>
              ) : batches.length === 0 ? (
                <div className="py-12 text-center text-sm text-slate-400">
                  No batches have been created yet. Launch one using the form on the left!
                </div>
              ) : (
                <div className="divide-y divide-slate-100 overflow-hidden">
                  {batches.map((b) => (
                    <Link
                      key={b.id}
                      href={`/batches/${encodeURIComponent(b.id)}`}
                      className="group block py-3.5 transition hover:bg-slate-50/70"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-xs font-bold text-slate-900 group-hover:text-indigo-600">
                            {b.id}
                          </p>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                            <span className="inline-flex items-center gap-1">
                              <Clock size={12} />
                              {formatDate(b.created_at)}
                            </span>
                            <span>•</span>
                            <span>
                              {b.completed_count ?? 0}/{b.total_count ?? b.targets?.length ?? 0} URLs done
                            </span>
                            {(b.failed_count ?? 0) > 0 && (
                              <>
                                <span>•</span>
                                <span className="font-semibold text-red-600">{b.failed_count} failed</span>
                              </>
                            )}
                            {b.allow_internal_discovery && (
                              <>
                                <span>•</span>
                                <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
                                  Discovery Enabled
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${statusClass(
                              b.status,
                            )}`}
                          >
                            crawl: {b.status}
                          </span>
                          {b.analysis_status && (
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${statusClass(
                                b.analysis_status,
                              )}`}
                            >
                              analysis: {b.analysis_status}
                            </span>
                          )}
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
