// Settings → Projects tracking panel (SPEC §21;
// step 9): the repo registry's editing surface. The
// registry is the harness-owned tracking metadata for
// browsed repos (lib/repo_state.py) — display name,
// expected publication, pinned, ignored, notes. Edits
// post a patch of the changed fields only, through the
// one mutation path; publication and exposure themselves
// are derived from the repos and are never edited here.
//
// Rendering shape (critic M-4): the registry runs to
// ~840 repos, and mounting every repo's editor at once
// put ~7,500 interactive controls and ~263 KB of text
// on the Settings route — the page's own weight defeated
// interaction with it. The panel now renders like the
// design's compact Settings form: a search field, a
// windowed list of one-line repo summaries, and each
// repo's editor mounted only while its row is expanded
// (or reached through search). The served registry is
// consumed whole and unchanged — windowing is a
// rendering decision only; every repo stays reachable
// and editable, none is hidden from the surface.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { SegmentedControl } from "@workhorse/kit/components/controls/SegmentedControl";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { api } from "../../lib/api";
import type { RepoRegistryEntry, ProjectsRegistryPayload } from "../../lib/api-types-code";
import { formatDateTime } from "../../lib/format";
import { expectedLabel } from "../../lib/labels";
import { sectionHref } from "../../lib/routing";
import { ErrorWell, SkeletonWell } from "../shared";

const panelTitleStyle: React.CSSProperties = {
  fontSize: "var(--wb-font-size-xs)",
  lineHeight: "var(--wb-line-height-xs)",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--wb-content-secondary)",
  marginTop: "var(--wb-space-32)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
  whiteSpace: "nowrap",
};

const inputStyle: React.CSSProperties = {
  background: "var(--wb-surface-2)",
  border: "1px solid var(--wb-border-default)",
  borderRadius: "var(--wb-radius-sm)",
  color: "var(--wb-content-primary)",
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
  padding: "var(--wb-space-8)",
  minHeight: "38px",
  width: "100%",
  minWidth: 0,
};

const fieldRowStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "140px 1fr",
  gap: "var(--wb-space-8) var(--wb-space-16)",
  alignItems: "center",
  padding: "var(--wb-space-8) 0",
};

type Expected = RepoRegistryEntry["expected"];

const EXPECTED_OPTIONS: { value: Expected; label: string }[] = [
  { value: "published", label: expectedLabel("published") },
  { value: "local_ok", label: expectedLabel("local_ok") },
  { value: "untracked", label: expectedLabel("untracked") },
];

function RegistryRow({ id, entry }: { id: string; entry: RepoRegistryEntry }) {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(entry.display_name);
  const [expected, setExpected] = useState<Expected>(entry.expected);
  const [pinned, setPinned] = useState(entry.pinned);
  const [ignored, setIgnored] = useState(entry.ignored);
  const [notes, setNotes] = useState(entry.notes);
  const [result, setResult] = useState<string | null>(null);

  const patch: Record<string, unknown> = {};
  if (displayName !== entry.display_name) patch.display_name = displayName;
  if (expected !== entry.expected) patch.expected = expected;
  if (pinned !== entry.pinned) patch.pinned = pinned;
  if (ignored !== entry.ignored) patch.ignored = ignored;
  if (notes !== entry.notes) patch.notes = notes;
  const dirty = Object.keys(patch).length > 0;

  const mutation = useMutation({
    mutationFn: () => api.updateProjectsRegistry({ id, patch }),
    onSuccess: (reply) => {
      const updated = (reply.payload as { registry?: RepoRegistryEntry } | null)?.registry;
      if (!updated) {
        setResult(reply.error ?? "the update was refused — nothing was written.");
        return;
      }
      // Reseed from the server's own returned entry (the
      // row is keyed by id only, so a registry refetch
      // never wipes another row's unsaved edits).
      setDisplayName(updated.display_name);
      setExpected(updated.expected);
      setPinned(updated.pinned);
      setIgnored(updated.ignored);
      setNotes(updated.notes);
      setResult("Saved.");
      void queryClient.invalidateQueries({ queryKey: ["projects-registry"] });
      void queryClient.invalidateQueries({ queryKey: ["projects-index"] });
    },
    onError: () => setResult("The update call failed — nothing was written."),
  });

  return (
    <div
      style={{
        border: "1px solid var(--wb-border-default)",
        borderRadius: "var(--wb-radius-md)",
        background: "var(--wb-surface-2)",
        padding: "var(--wb-space-16)",
        marginBottom: "var(--wb-space-12)",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "var(--wb-space-12)",
          alignItems: "baseline",
          flexWrap: "wrap",
          marginBottom: "var(--wb-space-8)",
        }}
      >
        <a
          href={sectionHref(id, "code")}
          className="mono"
          style={{
            color: "var(--wb-accent)",
            textDecoration: "none",
            fontWeight: 600,
            overflowWrap: "anywhere",
          }}
        >
          {id}
        </a>
        <span
          className="mono"
          style={{
            color: "var(--wb-content-muted)",
            fontSize: "var(--wb-font-size-xs)",
            overflowWrap: "anywhere",
          }}
        >
          {entry.root}
        </span>
        <span
          style={{
            color: "var(--wb-content-muted)",
            fontSize: "var(--wb-font-size-xs)",
            marginLeft: "auto",
          }}
        >
          first seen {formatDateTime(entry.first_seen)} · last seen{" "}
          {formatDateTime(entry.last_seen)}
        </span>
      </div>
      <div style={fieldRowStyle}>
        <span style={labelStyle}>Display name</span>
        <input
          style={inputStyle}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          aria-label={`Display name for ${id}`}
        />
      </div>
      <div style={fieldRowStyle}>
        <span style={labelStyle}>Expected</span>
        <SegmentedControl
          ariaLabel={`Expected publication for ${id}`}
          options={EXPECTED_OPTIONS}
          value={expected}
          onChange={(next) => setExpected(next as Expected)}
        />
      </div>
      <div style={fieldRowStyle}>
        <span style={labelStyle}>Pinned</span>
        <Toggle checked={pinned} onChange={setPinned} label="Pinned" />
      </div>
      <div style={fieldRowStyle}>
        <span style={labelStyle}>Ignored</span>
        <Toggle checked={ignored} onChange={setIgnored} label="Ignored" />
      </div>
      <div style={fieldRowStyle}>
        <span style={labelStyle}>Notes</span>
        <input
          style={inputStyle}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          aria-label={`Notes for ${id}`}
        />
      </div>
      <div
        style={{
          display: "flex",
          gap: "var(--wb-space-8)",
          alignItems: "center",
          paddingTop: "var(--wb-space-8)",
        }}
      >
        <Button disabled={!dirty || mutation.isPending} onClick={() => mutation.mutate()}>
          Save tracking
        </Button>
        {dirty ? (
          <span
            style={{ color: "var(--wb-content-secondary)", fontSize: "var(--wb-font-size-sm)" }}
          >
            Unsaved changes
          </span>
        ) : null}
        {result ? (
          <span role="status" style={{ color: "var(--wb-content-secondary)" }}>
            {result}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/** One repo's collapsed summary row: identity, root, and
 * the tracking posture at a glance. The row is the
 * expander — the full editor mounts under it only while
 * expanded, so the closed panel carries one control per
 * visible repo instead of one editor per repo. */
function RegistrySummaryRow({
  id,
  entry,
  expanded,
  onToggle,
}: {
  id: string;
  entry: RepoRegistryEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-expanded={expanded}
      onClick={onToggle}
      style={{
        display: "flex",
        gap: "var(--wb-space-12)",
        alignItems: "baseline",
        flexWrap: "wrap",
        width: "100%",
        textAlign: "left",
        background: "none",
        border: "none",
        borderBottom: "1px solid var(--wb-border-default)",
        padding: "var(--wb-space-8) 0",
        cursor: "pointer",
        font: "inherit",
        color: "var(--wb-content-primary)",
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--wb-content-muted)" }}>
        {expanded ? "▾" : "▸"}
      </span>
      <span className="mono" style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
        {entry.display_name || id}
      </span>
      <span
        className="mono"
        style={{
          color: "var(--wb-content-muted)",
          fontSize: "var(--wb-font-size-xs)",
          overflowWrap: "anywhere",
        }}
      >
        {entry.root}
      </span>
      <span
        style={{
          color: "var(--wb-content-muted)",
          fontSize: "var(--wb-font-size-xs)",
          marginLeft: "auto",
        }}
      >
        {expectedLabel(entry.expected)}
        {entry.pinned ? " · pinned" : ""}
        {entry.ignored ? " · ignored" : ""}
      </span>
    </button>
  );
}

/** Summary rows mount in windows of this size; "Show
 * more" grows the window. Search narrows the whole
 * registry first, so any repo is reachable by name
 * without paging. */
const WINDOW_FIRST = 25;
const WINDOW_STEP = 50;

export function ProjectsTrackingPanel() {
  const query = useQuery({
    queryKey: ["projects-registry"],
    queryFn: () => api.getProjectsRegistry({}),
  });
  const [search, setSearch] = useState("");
  const [windowSize, setWindowSize] = useState(WINDOW_FIRST);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const payload = query.data?.payload as unknown as ProjectsRegistryPayload | null;
  const ids = useMemo(() => (payload ? Object.keys(payload.projects).sort() : []), [payload]);
  const needle = search.trim().toLowerCase();
  const matched = useMemo(() => {
    if (!payload || !needle) return ids;
    return ids.filter((id) => {
      const entry = payload.projects[id];
      if (!entry) return false;
      return (
        id.toLowerCase().includes(needle) ||
        entry.display_name.toLowerCase().includes(needle) ||
        entry.root.toLowerCase().includes(needle)
      );
    });
  }, [payload, ids, needle]);
  const visible = matched.slice(0, windowSize);
  const toggleRow = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  return (
    <>
      <h2 style={panelTitleStyle}>Projects — tracking</h2>
      {query.isPending ? (
        <SkeletonWell label="the repo registry" />
      ) : query.isError || !payload ? (
        <ErrorWell
          section="Projects tracking"
          message={query.data?.error ?? "the repo registry did not answer."}
        />
      ) : ids.length === 0 ? (
        <p style={{ color: "var(--wb-content-muted)" }}>No projects in the registry yet.</p>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              gap: "var(--wb-space-12)",
              alignItems: "center",
              flexWrap: "wrap",
              marginBottom: "var(--wb-space-8)",
            }}
          >
            <input
              style={{ ...inputStyle, width: "320px", maxWidth: "100%" }}
              type="search"
              placeholder="Search projects by name or path…"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setWindowSize(WINDOW_FIRST);
              }}
              aria-label="Search projects in the registry"
            />
            <span style={{ color: "var(--wb-content-muted)", fontSize: "var(--wb-font-size-sm)" }}>
              <span className="num">{ids.length}</span> projects
              {needle ? (
                <>
                  {" · "}
                  <span className="num">{matched.length}</span> match
                  {matched.length === 1 ? "" : "es"}
                </>
              ) : null}
              {" · showing "}
              <span className="num">{visible.length}</span>
            </span>
          </div>
          {matched.length === 0 ? (
            <p style={{ color: "var(--wb-content-muted)" }}>
              No projects match "{search.trim()}".
            </p>
          ) : (
            visible.map((id) => {
              const entry = payload.projects[id];
              if (!entry) return null;
              const isOpen = expanded.has(id);
              return (
                <div key={id}>
                  <RegistrySummaryRow
                    id={id}
                    entry={entry}
                    expanded={isOpen}
                    onToggle={() => toggleRow(id)}
                  />
                  {isOpen ? (
                    <div style={{ paddingTop: "var(--wb-space-12)" }}>
                      <RegistryRow id={id} entry={entry} />
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
          {windowSize < matched.length ? (
            <div style={{ paddingTop: "var(--wb-space-12)" }}>
              <Button
                variant="secondary"
                onClick={() => setWindowSize((n) => n + WINDOW_STEP)}
              >
                Show more — <span className="num">{matched.length - visible.length}</span> more
                projects
              </Button>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
