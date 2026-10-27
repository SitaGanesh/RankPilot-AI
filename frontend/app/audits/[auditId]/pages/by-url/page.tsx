"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ExternalLink, Loader2, Radar } from "lucide-react";
import Link from "next/link";
import { createAudit, getAuditPageReportByUrl } from "@/lib/api";
import type { PageReportAvailability } from "@/lib/api";

const STATUS_COPY: Record<string, { label: string; tone: string; note: string }> = {
  pending: {
    label: "Queued",
    tone: "text-blue-700 bg-blue-50 border-blue-200",
    note: "This URL is known to the crawler but has not been deeply audited yet. It will be analyzed when the crawl reaches it.",
  },
  processing: {
    label: "In progress",
    tone: "text-amber-700 bg-amber-50 border-amber-200",
    note: "This URL is currently being fetched or analyzed. Reload this tab in a moment to see the saved report.",
  },
  failed: {
    label: "Audit failed",
    tone: "text-red-700 bg-red-50 border-red-200",
    note: "The audit attempt for this URL did not complete. You can request a separate audit below.",
  },
  skipped: {
    label: "Not crawled",
    tone: "text-slate-600 bg-slate-100 border-slate-200",
    note: "This URL was discovered as a link but fell outside the configured crawl scope (depth or robots rules), so no page report exists.",
  },
  unavailable: {
    label: "Not audited",
    tone: "text-slate-600 bg-slate-100 border-slate-200",
    note: "No audit has run for this URL. Request a separate audit to analyze it.",
  },
};

export default function PageReportByUrlRoute() {
  return (
    <Suspense
      fallback={
        <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-500">
          <Loader2 className="animate-spin" />
        </main>
      }
    >
      <PageReportByUrlContent />
    </Suspense>
  );
}

function PageReportByUrlContent() {
  const { auditId } = useParams<{ auditId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [message, setMessage] = useState("Locating the persisted page report…");
  const [result, setResult] = useState<PageReportAvailability | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

  const url = searchParams.get("url") || "";

  useEffect(() => {
    if (!url) {
      setMessage("A URL is required to open a page report.");
      return;
    }
    getAuditPageReportByUrl(auditId, url)
      .then((res) => {
        if (res.page) {
          router.replace(`/audits/${auditId}/pages/${res.page.id}`);
          return;
        }
        setResult(res);
        setMessage("");
      })
      .catch((caught) => setMessage(caught instanceof Error ? caught.message : "The page report is unavailable."));
  }, [auditId, router, url]);

  const handleRequestAudit = useCallback(async () => {
    if (!url) return;
    setRequesting(true);
    setRequestError(null);
    try {
      const created = await createAudit(url, { audit_type: "page" });
      router.push(`/audits/${created.id}`);
    } catch (caught) {
      setRequestError(caught instanceof Error ? caught.message : "The audit could not be requested.");
    } finally {
      setRequesting(false);
    }
  }, [router, url]);

  if (!url) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 p-6 text-center text-sm text-slate-600">
        {message}
      </main>
    );
  }

  if (message) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 p-6 text-center text-sm text-slate-600">
        <div>
          {message}
          <Loader2 size={18} className="mx-auto mt-3 animate-spin text-indigo-600" />
        </div>
      </main>
    );
  }

  const info = STATUS_COPY[result?.availability || "unavailable"] || STATUS_COPY.unavailable;
  const crawlStatus = result?.crawl_url?.status;
  const responseStatus = result?.crawl_url?.response_status;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-5">
        <nav className="flex items-center justify-between text-xs text-slate-500">
          <Link href={`/audits/${auditId}`} className="inline-flex items-center gap-1 font-semibold hover:text-indigo-600">
            <ArrowLeft size={14} /> Back to live audit
          </Link>
          {url && (
            <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-indigo-600">
              Open live URL <ExternalLink size={13} />
            </a>
          )}
        </nav>

        <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-indigo-600">Page report</p>
          <h1 className="mt-2 break-all text-xl font-semibold">{url}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-semibold ${info.tone}`}>
              {info.label}
            </span>
            {crawlStatus && (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-slate-600">
                crawl status: {crawlStatus}
              </span>
            )}
            {responseStatus && (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-slate-600">
                HTTP {responseStatus}
              </span>
            )}
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">{info.note}</p>
          {result?.crawl_url?.error && (
            <p className="mt-2 font-mono text-xs text-red-600">{result.crawl_url.error}</p>
          )}
        </header>

        <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-5">
          <div className="flex items-start gap-3">
            <Radar className="mt-0.5 h-5 w-5 shrink-0 text-indigo-600" />
            <div className="space-y-3">
              <div>
                <h2 className="text-sm font-bold text-indigo-950">Request a separate audit for this URL</h2>
                <p className="mt-1 text-xs leading-5 text-indigo-900/80">
                  Linking does not trigger crawling. Requesting an audit runs the existing audit workflow for this URL
                  alone and opens its live workspace; the saved report remains available afterwards.
                </p>
              </div>
              {requestError && <p className="text-xs text-red-600">{requestError}</p>}
              <button
                onClick={handleRequestAudit}
                disabled={requesting}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-60"
              >
                {requesting ? "Requesting…" : "Request audit for this URL"}
              </button>
            </div>
          </div>
        </section>

        <p className="text-xs leading-5 text-slate-500">
          This page reads persisted audit data only. Nothing here reruns the original crawl.
        </p>
      </div>
    </main>
  );
}
