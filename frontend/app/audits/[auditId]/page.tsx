"use client";

import { Suspense } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";

const LiveAuditWorkspace = dynamic(
  () => import("@/components/audit-workspace").then((mod) => mod.LiveAuditWorkspace),
  {
    ssr: false,
    loading: () => (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-900 text-slate-400 font-mono text-xs">
        Loading live audit workspace...
      </div>
    ),
  }
);

export default function AuditWorkspacePage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen w-screen flex items-center justify-center bg-slate-900 text-slate-400 font-mono text-xs">
          Loading live audit workspace...
        </div>
      }
    >
      <AuditWorkspaceContent />
    </Suspense>
  );
}

function AuditWorkspaceContent() {
  const params = useParams<{ auditId: string }>();
  const auditId = params?.auditId;

  if (!auditId) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-900 text-slate-400 font-mono text-xs">
        Invalid or missing audit ID.
      </div>
    );
  }

  return <LiveAuditWorkspace auditId={auditId} />;
}
