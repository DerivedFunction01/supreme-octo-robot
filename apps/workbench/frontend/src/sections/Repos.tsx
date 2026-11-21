import { useState } from "react";
import { SegmentedControl } from "@kit/components/SegmentedControl";
import { Button } from "@kit/components/Button";
import { Sheet } from "@kit/components/Sheet";
import { Toggle } from "@kit/components/Toggle";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { DiffFile, DiffMode, ProjectDiff } from "../lib/types";
import {
  ActionRow,
  Chev,
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Sub,
  Subtitle,
  TOGGLE_LABEL_SR_ONLY,
  Val,
} from "../components/ui";

// Frame 14 · Code — the current project's git facet
// (SPEC §21: the Repos list destination is retired; a
// project is entered from Home/Projects and its Code
// section is this surface): status & worktrees, with
// the Status / Files / History segmented control the
// explorer frames share.

function SweepChip({ sweep }: { sweep: "swept" | "degraded" | "manifest-only" }) {
  const map = {
    swept: { label: "Swept", bg: "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)", fg: "var(--wb-status-implemented-text)", dot: "var(--wb-okabe-bluish-green)" },
    degraded: { label: "Degraded", bg: "color-mix(in srgb, var(--wb-okabe-orange) 16%, transparent)", fg: "var(--wb-status-stale-text)", dot: "var(--wb-okabe-orange)" },
    "manifest-only": { label: "Manifest only", bg: "var(--wb-surface-sunken)", fg: "var(--wb-content-secondary)", dot: "var(--wb-content-muted)" },
  } as const;
  const s = map[sweep];
  return (
    <span
      className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
      style={{ backgroundColor: s.bg, color: s.fg }}
    >
      <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: s.dot }} />
      {s.label}
    </span>
  );
}

function DiffFiles({ files }: { files: DiffFile[] }) {
  if (files.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
        No file changes in this view.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {files.map((f) => (
        <div
          key={f.path}
          className="overflow-hidden"
          style={{
            backgroundColor: "var(--wb-surface-2)",
            border: "1px solid var(--wb-border-default)",
            borderRadius: "var(--wb-radius-lg)",
          }}
        >
          <div
            className="flex items-center gap-2 px-3.5 py-2 font-mono text-xs font-bold"
            style={{ borderBottom: "1px solid var(--wb-border-default)" }}
          >
            <span className="min-w-0 truncate">{f.path}</span>
            <span className="ml-auto shrink-0" style={{ color: "var(--wb-content-secondary)" }}>
              +{f.adds} · −{f.dels}
            </span>
          </div>
          <div className="overflow-x-auto p-3 font-mono text-xs leading-[1.8]" style={{ whiteSpace: "pre" }}>
            {f.lines.map((l, i) => (
              <div
                key={i}
                style={{
                  backgroundColor:
                    l.kind === "add"
                      ? "color-mix(in srgb, var(--wb-okabe-bluish-green) 16%, transparent)"
                      : l.kind === "del"
                        ? "color-mix(in srgb, var(--wb-okabe-vermilion) 14%, transparent)"
                        : undefined,
                  borderRadius: 4,
                  padding: "0 4px",
                }}
              >
                {l.kind === "add" ? "+ " : l.kind === "del" ? "- " : "  "}
                {l.text}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function DiffPanel({ repoSlug }: { repoSlug: string }) {
  const a = useAdapter();
  const modes = a.diffModes(repoSlug);
  const [mode, setMode] = useState<DiffMode>("working");
  const diff: ProjectDiff = a.projectDiff(repoSlug, mode);
  return (
    <div>
      <div className="mb-3.5">
        <SegmentedControl
          ariaLabel="Diff mode"
          options={modes.map((m) => ({ value: m.mode, label: m.label }))}
          value={mode}
          onChange={(v) => setMode(v as DiffMode)}
        />
      </div>
      <p className="mb-3 text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
        {diff.label}
      </p>
      {diff.note ? (
        <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
          {diff.note}
        </p>
      ) : null}
      {diff.mode === "uncommitted" ? (
        <>
          <GroupLabel>Staged</GroupLabel>
          <DiffFiles files={diff.staged ?? []} />
          <GroupLabel>Unstaged</GroupLabel>
          <DiffFiles files={diff.unstaged ?? []} />
        </>
      ) : (
        <DiffFiles files={diff.files} />
      )}
    </div>
  );
}

const repoInputStyle: React.CSSProperties = {
  backgroundColor: "var(--wb-surface-sunken)",
  color: "var(--wb-content-primary)",
  borderRadius: 9,
  padding: "6px 10px",
  fontSize: 13.5,
};

export function RepoDetail({ repoSlug }: { repoSlug: string }) {
  useStoreVersion();
  const a = useAdapter();
  const { navigate } = useNav();
  const [tab, setTab] = useState<"status" | "files" | "history" | "diff">("status");
  const [openWorktree, setOpenWorktree] = useState<string | null>(null);
  const [trackingOpen, setTrackingOpen] = useState(false);
  const [tName, setTName] = useState("");
  const [tExpected, setTExpected] = useState("");
  const [tNotes, setTNotes] = useState("");
  const [tPinned, setTPinned] = useState(false);
  const [tIgnored, setTIgnored] = useState(false);
  const repo = a.repo(repoSlug);
  if (!repo) {
    return (
      <div className="px-[26px] py-[22px]">
        <Subtitle>That repo is not in the swept registry.</Subtitle>
      </div>
    );
  }
  const tracking = repo.tracking ?? { expected: "", pinned: false, ignored: false, notes: "" };
  const worktreeDetail = openWorktree ? a.worktreeDetail(repo.slug, openWorktree) : undefined;
  return (
    <div className="px-[26px] py-[22px]">
      <button
        type="button"
        onClick={() => navigate({ section: "home" })}
        className="mb-3 text-sm font-semibold"
        style={{ color: "var(--wb-accent)" }}
      >
        ‹ Projects
      </button>
      <LargeTitle>{repo.name}</LargeTitle>
      <Subtitle>Repo status · served from git</Subtitle>
      <div className="mb-[18px]">
        <SegmentedControl
          ariaLabel="Repo view"
          options={[
            { value: "status", label: "Status" },
            { value: "files", label: "Files" },
            { value: "diff", label: "Diff" },
            { value: "history", label: "History" },
          ]}
          value={tab}
          onChange={(v) => {
            if (v === "files") {
              navigate({ section: "browse", repo: repo.slug, path: [] });
            } else {
              setTab(v as "status" | "history" | "diff");
            }
          }}
        />
      </div>
      {tab === "status" ? (
        <>
          <GroupLabel>Status</GroupLabel>
          <Group>
            <Row>
              <Lab>Branch</Lab>
              <Val mono>{repo.branch}</Val>
            </Row>
            <Row>
              <Lab>Sync</Lab>
              <Val>{repo.syncLabel}</Val>
            </Row>
            <Row last>
              <Lab>Working tree</Lab>
              {repo.modifiedCount > 0 ? (
                <span
                  className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                  style={{
                    backgroundColor: "color-mix(in srgb, var(--wb-okabe-orange) 16%, transparent)",
                    color: "var(--wb-status-stale-text)",
                  }}
                >
                  <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: "var(--wb-okabe-orange)" }} />
                  {repo.modifiedCount} files modified
                </span>
              ) : (
                <Val>Clean</Val>
              )}
            </Row>
          </Group>
          <GroupLabel>Worktrees · {repo.worktrees.length}</GroupLabel>
          <Group>
            {repo.worktrees.map((w, i) => (
              <Row
                key={w.path}
                last={i === repo.worktrees.length - 1}
                selected={openWorktree === w.path}
                onClick={() => setOpenWorktree(openWorktree === w.path ? null : w.path)}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[14.5px] font-medium">{w.label}</span>
                  <Sub truncate>
                    <span className="font-mono">{w.path}</span>
                  </Sub>
                </span>
                {w.dirty && w.dirty > 0 ? (
                  <span
                    className="ml-auto inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--wb-okabe-orange) 16%, transparent)",
                      color: "var(--wb-status-stale-text)",
                    }}
                  >
                    Dirty · {w.dirty}
                  </span>
                ) : (
                  <span
                    className="ml-auto inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)",
                      color: "var(--wb-status-implemented-text)",
                    }}
                  >
                    Clean
                  </span>
                )}
                <Chev />
              </Row>
            ))}
          </Group>
          {worktreeDetail ? (
            <>
              <GroupLabel>Worktree · {worktreeDetail.label}</GroupLabel>
              <Group>
                <Row>
                  <Lab>Branch</Lab>
                  <Val mono>{worktreeDetail.branch}</Val>
                </Row>
                <Row>
                  <Lab>Active plan</Lab>
                  <Val>{worktreeDetail.activePlan ?? "—"}</Val>
                </Row>
                <Row last={worktreeDetail.changedFiles.length === 0}>
                  <Lab>Changed files</Lab>
                  <Val>{worktreeDetail.changedFiles.length}</Val>
                </Row>
                {worktreeDetail.changedFiles.map((p, i) => (
                  <Row key={p} last={i === worktreeDetail.changedFiles.length - 1}>
                    <span className="min-w-0 truncate font-mono text-[12.5px]">{p}</span>
                  </Row>
                ))}
              </Group>
              <div className="mt-3">
                <Group>
                  <ActionRow
                    label="Browse this worktree's files"
                    last
                    onClick={() => navigate({ section: "browse", repo: repo.slug, path: [] })}
                  />
                </Group>
              </div>
            </>
          ) : null}
          <GroupLabel>Tracking</GroupLabel>
          <Group>
            <Row>
              <Lab>Display name</Lab>
              <Val>{repo.name}</Val>
            </Row>
            <Row>
              <Lab>Expected</Lab>
              <Val>{tracking.expected || "—"}</Val>
            </Row>
            <Row>
              <Lab>Pinned</Lab>
              <Val>{tracking.pinned ? "Yes" : "No"}</Val>
            </Row>
            <Row>
              <Lab>Ignored</Lab>
              <Val>{tracking.ignored ? "Yes" : "No"}</Val>
            </Row>
            <Row>
              <Lab>Notes</Lab>
              <Val>{tracking.notes || "—"}</Val>
            </Row>
            <ActionRow
              label="Edit tracking…"
              last
              onClick={() => {
                setTName(repo.name);
                setTExpected(tracking.expected);
                setTNotes(tracking.notes);
                setTPinned(tracking.pinned);
                setTIgnored(tracking.ignored);
                setTrackingOpen(true);
              }}
            />
          </Group>
        </>
      ) : tab === "diff" ? (
        <DiffPanel repoSlug={repo.slug} />
      ) : (
        <>
          <GroupLabel>History</GroupLabel>
          <Group>
            {repo.history.map((h, i) => (
              <Row key={h.sha} last={i === repo.history.length - 1}>
                <span className="min-w-0">
                  <span className="block truncate text-[14.5px] font-medium">{h.title}</span>
                  <Sub>{h.when}</Sub>
                </span>
                <Val mono>{h.sha}</Val>
              </Row>
            ))}
          </Group>
        </>
      )}

      <Sheet
        open={trackingOpen}
        title="Edit tracking"
        onClose={() => setTrackingOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTrackingOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!tName.trim()}
              onClick={() => {
                void a.updateRepoTracking(repo.slug, {
                  name: tName,
                  expected: tExpected,
                  notes: tNotes,
                  pinned: tPinned,
                  ignored: tIgnored,
                });
                setTrackingOpen(false);
              }}
            >
              Save tracking
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Display name</span>
            <input aria-label="Display name" value={tName} onChange={(e) => setTName(e.target.value)} style={repoInputStyle} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Expected</span>
            <input
              aria-label="Expected"
              value={tExpected}
              onChange={(e) => setTExpected(e.target.value)}
              placeholder="e.g. On the daily sweep"
              style={repoInputStyle}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Notes</span>
            <textarea
              aria-label="Tracking notes"
              value={tNotes}
              onChange={(e) => setTNotes(e.target.value)}
              rows={3}
              style={{ ...repoInputStyle, resize: "vertical" }}
            />
          </label>
          <Group>
            <Row>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">Pinned</span>
                <Sub>Kept at the top of the registry</Sub>
              </span>
              <span className="ml-auto">
                <Toggle checked={tPinned} onChange={setTPinned} label="Pinned" className={TOGGLE_LABEL_SR_ONLY} />
              </span>
            </Row>
            <Row last>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">Ignored</span>
                <Sub>Skipped by the sweep's attention</Sub>
              </span>
              <span className="ml-auto">
                <Toggle checked={tIgnored} onChange={setTIgnored} label="Ignored" className={TOGGLE_LABEL_SR_ONLY} />
              </span>
            </Row>
          </Group>
        </div>
      </Sheet>
    </div>
  );
}
