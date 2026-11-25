// Code — the per-project git facet (SPEC §21): one
// project's Status | Files | History behind tabs, with
// a checkout selector where the project has linked
// worktrees. This surface replaces the retired Repos
// destination: the project is the object, git is its
// facet, and every value renders served — the backend
// does the work (the unified index in lib/derived/
// projects.py, the Code routes in serving.py).

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { api } from "../../lib/api";
import type {
  ProjectIndexRow,
  RepoHistoryPayload,
  RepoStatusPayload,
} from "../../lib/api-types-code";
import { formatDate, formatRelative, formatShortHash } from "../../lib/format";
import { indexPayloadOf, indexRow, useProjectIndex } from "../../lib/projectsIndex";
import { homeHref, sectionHref } from "../../lib/routing";
import { EmptyWell, ErrorWell, metaStyle, SectionTitle, SkeletonWell } from "../shared";
import { CheckoutContext } from "./checkoutContext";
import { FilesTab } from "./FilesTab";
import { HistoryTab } from "./HistoryTab";
import { AheadBehind, DirtyMark, ExposureMark, PublicationMark, SyncMark } from "./marks";
import { StatusTab } from "./StatusTab";

type CodeTab = "status" | "files" | "history";

const TAB_OPTIONS: { value: CodeTab; label: string }[] = [
  { value: "status", label: "Status" },
  { value: "files", label: "Files" },
  { value: "history", label: "History" },
];

function StreakChip({ label, since }: { label: string; since: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: "24px",
        padding: "0 var(--ui-space-8)",
        borderRadius: "var(--ui-radius-pill)",
        border: "1px solid var(--ui-status-stale)",
        color: "var(--ui-status-stale-text)",
        fontSize: "var(--ui-font-size-xs)",
        lineHeight: "var(--ui-line-height-xs)",
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}
    >
      ◷ {label} since {formatDate(since)} ({formatRelative(since)})
    </span>
  );
}

function CodeHeader({
  slug,
  row,
  status,
  history,
}: {
  slug: string;
  row: ProjectIndexRow;
  status: RepoStatusPayload;
  history: RepoHistoryPayload | null;
}) {
  const name = status.registry?.display_name || row.name;
  return (
    <header style={{ marginBottom: "var(--ui-space-16)" }}>
      <p style={{ margin: "0 0 var(--ui-space-4)" }}>
        <a
          href={sectionHref(slug, "overview")}
          style={{
            color: "var(--ui-accent)",
            textDecoration: "none",
            fontSize: "var(--ui-font-size-sm)",
          }}
        >
          ← Project overview
        </a>
      </p>
      <SectionTitle style={{ margin: 0 }}>{name}</SectionTitle>
      <p
        className="mono"
        style={{
          color: "var(--ui-content-muted)",
          fontSize: "var(--ui-font-size-xs)",
          overflowWrap: "anywhere",
          margin: "var(--ui-space-4) 0 var(--ui-space-12)",
        }}
      >
        {status.id} · {status.root}
        {status.is_worktree ? " · linked worktree" : ""}
      </p>
      {status.error ? (
        <p role="alert" style={{ color: "var(--ui-danger)" }}>
          This checkout's state could not be derived — {status.error}
        </p>
      ) : (
        <>
          <p
            style={{
              display: "flex",
              gap: "var(--ui-space-8)",
              alignItems: "baseline",
              flexWrap: "wrap",
              margin: "0 0 var(--ui-space-8)",
              fontSize: "var(--ui-font-size-sm)",
            }}
          >
            <span className="mono" style={{ fontWeight: 600 }}>
              {status.branch ?? "detached"}
            </span>
            <span className="mono" style={metaStyle}>
              {formatShortHash(status.head_short ?? status.head)}
            </span>
            <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
              {status.head_subject ?? ""}
            </span>
          </p>
          <p
            style={{
              display: "flex",
              gap: "var(--ui-space-8)",
              alignItems: "center",
              flexWrap: "wrap",
              margin: 0,
            }}
          >
            <PublicationMark summary={status} />
            <SyncMark summary={status} />
            <ExposureMark summary={status} />
            <AheadBehind summary={status} />
            <DirtyMark summary={status} />
            {history?.dirty_since ? <StreakChip label="Dirty" since={history.dirty_since} /> : null}
            {history?.ahead_since ? <StreakChip label="Ahead" since={history.ahead_since} /> : null}
            {status.registry?.notes ? (
              <span style={metaStyle}>Registry note: {status.registry.notes}</span>
            ) : null}
          </p>
        </>
      )}
    </header>
  );
}

function CheckoutSelector({
  row,
  checkout,
  onChange,
}: {
  row: ProjectIndexRow;
  checkout: string | undefined;
  onChange: (next: string | undefined) => void;
}) {
  if (row.checkouts.length <= 1) return null;
  const options = row.checkouts.map((entry) => ({
    value: entry.id,
    label: entry.is_worktree ? entry.id.split("/").pop() ?? entry.id : "Main",
  }));
  const value = checkout ?? row.checkouts[0]?.id;
  return (
    <div style={{ marginBottom: "var(--ui-space-16)" }}>
      <SegmentedControl
        ariaLabel="Checkout"
        options={options}
        value={value ?? ""}
        onChange={(next) => {
          const main = row.checkouts[0]?.id;
          onChange(next === main ? undefined : next);
        }}
      />
    </div>
  );
}

export function CodeSection({ slug }: { slug: string }) {
  const [tab, setTab] = useState<CodeTab>("status");
  const [checkout, setCheckout] = useState<string | undefined>(undefined);

  const indexQuery = useProjectIndex();
  const row = indexRow(indexPayloadOf(indexQuery.data), slug);

  const statusQuery = useQuery({
    queryKey: ["code-status", slug, checkout],
    queryFn: () => api.getCodeStatus({ projectId: slug, checkout }),
    enabled: row != null && !row.missing,
  });
  const status = statusQuery.data?.payload as unknown as RepoStatusPayload | null;

  const historyQuery = useQuery({
    queryKey: ["code-history", slug],
    queryFn: () => api.getCodeHistory({ projectId: slug }),
    enabled: row != null && !row.missing,
  });
  const history = historyQuery.data?.payload as unknown as RepoHistoryPayload | null;

  if (row?.missing) {
    return (
      <div data-anchor="code/missing">
        <p style={{ margin: "0 0 var(--ui-space-4)" }}>
          <a
            href={sectionHref(slug, "overview")}
            style={{ color: "var(--ui-accent)", textDecoration: "none" }}
          >
            ← Project overview
          </a>
        </p>
        <SectionTitle>{row.registry?.display_name || slug}</SectionTitle>
        <EmptyWell>
          ⚠ Missing — the registry knows this project (root{" "}
          <span className="mono">{row.root ?? slug}</span>) but discovery did not find it on disk.
        </EmptyWell>
      </div>
    );
  }

  if (!indexQuery.isPending && row == null) {
    return (
      <div data-anchor="code/view">
        <ErrorWell section="Code" message={`project ${slug} is not in the index.`} />
      </div>
    );
  }

  return (
    <section data-anchor="code/section">
      <div data-anchor="code/view">
        {statusQuery.isPending || row == null ? (
          <SkeletonWell label="the project" />
        ) : statusQuery.isError || !status ? (
          <ErrorWell
            section="Code"
            message={statusQuery.data?.error ?? "the code status did not answer."}
          />
        ) : (
          <>
            <CodeHeader slug={slug} row={row} status={status} history={history} />
            <CheckoutSelector row={row} checkout={checkout} onChange={setCheckout} />
            <div style={{ marginBottom: "var(--ui-space-16)" }}>
              <SegmentedControl
                ariaLabel="Code view"
                options={TAB_OPTIONS}
                value={tab}
                onChange={(next) => setTab(next as CodeTab)}
              />
            </div>
            <CheckoutContext.Provider value={checkout}>
              {tab === "status" ? (
                <StatusTab status={status} />
              ) : tab === "files" ? (
                <FilesTab projectId={slug} />
              ) : (
                <HistoryTab projectId={slug} />
              )}
            </CheckoutContext.Provider>
          </>
        )}
      </div>
    </section>
  );
}

/** The Overview of a project the sweep does not carry:
 * a repository-only (or missing) project's identity and
 * code summary, with the work sections' honest absence.
 * The full Code surface is one tap away. */
export function RepoOnlyOverview({ slug }: { slug: string }) {
  const indexQuery = useProjectIndex();
  const row = indexRow(indexPayloadOf(indexQuery.data), slug);
  if (indexQuery.isPending) return <SkeletonWell label="the project" />;
  if (row == null) {
    return (
      <ErrorWell section="Overview" message={`project ${slug} is not in the index.`} />
    );
  }
  const summary = row.code
    ? {
        ...row.code,
        id: row.id,
        name: row.name,
        root: row.root ?? "",
        is_worktree: false,
        parent_id: null,
        registry: row.registry,
        remote_view_as_of: null,
        remote_stale: false,
      }
    : null;
  return (
    <section data-anchor="code/repo-only-overview">
      <SectionTitle style={{ marginTop: 0 }}>{row.name}</SectionTitle>
      <p className="mono" style={{ ...metaStyle, overflowWrap: "anywhere" }}>
        {row.id} · {row.root ?? ""}
      </p>
      <p style={{ color: "var(--ui-content-secondary)" }}>
        {row.missing
          ? "Missing — the registry knows this project, but discovery did not find it on disk."
          : "Repository only — this checkout carries no workbench manifest, so it has no Entries, Plans, Todos, or Board. Its git surface lives in Code."}
      </p>
      {summary && !row.missing ? (
        <>
          <p
            style={{
              display: "flex",
              gap: "var(--ui-space-8)",
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <span className="mono" style={{ fontWeight: 600 }}>
              {summary.branch ?? "detached"}
            </span>
            <span className="mono" style={metaStyle}>
              {formatShortHash(summary.head_short ?? summary.head)}
            </span>
            <PublicationMark summary={summary} />
            <SyncMark summary={summary} />
            <ExposureMark summary={summary} />
            <AheadBehind summary={summary} />
            <DirtyMark summary={summary} />
          </p>
          <p>
            <a
              href={sectionHref(slug, "code")}
              style={{ color: "var(--ui-accent)", textDecoration: "none" }}
            >
              Open Code →
            </a>
          </p>
        </>
      ) : null}
    </section>
  );
}

/** A section route whose slug the sweep does not carry:
 * the unified index decides what the project is. A
 * repository-only project serves Code and its Overview;
 * the work sections render their honest absence; an id
 * in neither enumeration keeps the not-in-sweep answer. */
export function UnknownProjectSection({
  slug,
  section,
}: {
  slug: string;
  section: string;
}) {
  const indexQuery = useProjectIndex();
  if (indexQuery.isPending) return <SkeletonWell label="the project" />;
  const row = indexRow(indexPayloadOf(indexQuery.data), slug);
  if (row == null) {
    return (
      <p style={{ color: "var(--ui-content-secondary)" }}>
        Project <span className="mono">{slug}</span> is not in the current sweep.{" "}
        <a
          href={homeHref()}
          style={{
            color: "var(--ui-accent)",
            textDecoration: "underline",
            textUnderlineOffset: "0.14em",
          }}
        >
          Back to projects
        </a>
      </p>
    );
  }
  if (section === "code") return <CodeSection slug={slug} />;
  if (section === "overview") return <RepoOnlyOverview slug={slug} />;
  return (
    <section data-anchor="code/repo-only-absence">
      <SectionTitle style={{ marginTop: 0 }}>{row.name}</SectionTitle>
      <EmptyWell>
        {row.missing
          ? "This project is missing on disk — there is nothing to show here."
          : "Repository only — this checkout carries no workbench manifest, so this section does not exist for it. Its git surface lives in Code."}
      </EmptyWell>
      {!row.missing ? (
        <p>
          <a
            href={sectionHref(slug, "code")}
            style={{ color: "var(--ui-accent)", textDecoration: "none" }}
          >
            Open Code →
          </a>
        </p>
      ) : null}
    </section>
  );
}

/** The legacy #/repos/<id> hash (SPEC §21): resolve the
 * census id to its canonical project through the index
 * and land on that project's Code section. */
export function LegacyReposRedirect({ repoId }: { repoId: string | null }) {
  const indexQuery = useProjectIndex();
  const payload = indexPayloadOf(indexQuery.data);
  const row =
    repoId == null
      ? null
      : (payload?.projects.find(
          (entry) => entry.id === repoId || entry.checkouts.some((c) => c.id === repoId),
        ) ?? null);
  useEffect(() => {
    if (row) {
      window.location.replace(sectionHref(row.id, "code"));
    } else if (payload && repoId == null) {
      window.location.replace(homeHref());
    }
  }, [row, payload, repoId]);
  if (indexQuery.isPending) return <SkeletonWell label="the project index" />;
  if (repoId != null && payload && row == null) {
    return (
      <ErrorWell section="Code" message={`repo ${repoId} is not in the project index.`} />
    );
  }
  return <SkeletonWell label="the project index" />;
}
