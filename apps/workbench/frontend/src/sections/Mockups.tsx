import { useEffect, useState } from "react";
import { useIsPhone } from "@kit/lib/responsive";
import { ArmConfirm } from "@kit/components/shell/ArmConfirm";
import { Button } from "@kit/components/controls/Button";
import { Frame } from "@kit/components/shell/Frame";
import { Sheet } from "@kit/components/shell/Sheet";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { EntryPageResult } from "../lib/seam";
import type { FeedSegmentBlock } from "../lib/feeds";
import type { Entry, RuledStatus } from "../lib/types";
import { SegmentBlocks } from "./SegmentBlocks";
import {
  ActionRow,
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  ReviewBadge,
  Row,
  RuledChip,
  Sub,
  Subtitle,
  Val,
} from "../components/ui";

// Frames 2–3 · Mockups + drill-in. Frame 2: filter chips over
// the project's mockup entries, each a kit Frame (PreviewWell
// inside unified chrome — the kit sheet's one ruled
// exception). Frame 3: the drill-in — the entry's own
// page in the stage (W1: served over the byte route, not
// the schematic), disposition actions (lifecycle verbs, so they route through
// the kit's ArmConfirm guard), State / Approval / Review log.

export function PickChip({
  label,
  on,
  onPress,
}: {
  label: string;
  on: boolean;
  onPress: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onPress}
      className="max-w-full shrink-0 truncate rounded-full px-3 py-1 text-xs font-semibold whitespace-nowrap"
      style={{
        backgroundColor: on ? "var(--wb-accent)" : "var(--wb-surface-2)",
        border: `1px solid ${on ? "var(--wb-accent)" : "var(--wb-border-strong)"}`,
        color: on ? "var(--wb-on-accent)" : "var(--wb-content-secondary)",
      }}
    >
      {label}
    </button>
  );
}

/** The PreviewWell's specimen: a wireframe of the mocked
 *  surface, rendered in the specimen's own tones. */
function Specimen({ entry, mode }: { entry: Entry; mode: "Light" | "Dark" }) {
  const dark = mode === "Dark";
  const bar = dark ? "#3a3f2c" : "#59652c";
  const line = dark ? "#565b45" : "#ffffff";
  const seed = entry.id.length * 7 + entry.title.length;
  return (
    <div
      data-mode={dark ? "dark" : "light"}
      className="h-full w-full p-3"
      style={{ backgroundColor: dark ? "#22251a" : "var(--wb-surface-sunken)", borderRadius: "var(--wb-radius-md)" }}
    >
      <div className="mb-2 h-3.5 rounded" style={{ width: `${34 + (seed % 20)}%`, backgroundColor: bar }} />
      <div className="mb-[7px] h-[9px] rounded" style={{ width: "86%", backgroundColor: line, opacity: 0.9 }} />
      <div className="mb-[7px] h-[9px] rounded" style={{ width: "68%", backgroundColor: line, opacity: 0.9 }} />
      <div className="mt-2.5 flex gap-[7px]">
        {["#67742f", "#0f766e", "#0072B2", "#D55E00"].map((c) => (
          <div key={c} className="h-[34px] w-[52px] rounded" style={{ backgroundColor: c }} />
        ))}
      </div>
      <div className="mt-2.5 h-[9px] rounded" style={{ width: "56%", backgroundColor: line, opacity: 0.9 }} />
    </div>
  );
}

/** The drill-in stage: the entry's own document,
 *  rendered in place. A text document arrives as served
 *  segments (the segment feed) and renders natively —
 *  math nodes typeset by the kit's Math component. A
 *  rendered page (an HTML main file) is served over the
 *  byte route and rendered as a document in a sandboxed
 *  frame (the viewer's PreviewStage form) — the page
 *  itself, never a schematic of it. Freshness keys on
 *  the entry's recorded state hash, so a rebuilt page
 *  renders its new bytes on the next open. A refusal —
 *  held by reference, byte route down — shows its reason
 *  in the stage, never a partial page. */
function EntryPageStage({ entry }: { entry: Entry }) {
  const a = useAdapter();
  const [page, setPage] = useState<EntryPageResult | null>(null);
  const [segments, setSegments] = useState<FeedSegmentBlock[] | null>(null);
  useEffect(() => {
    let live = true;
    setPage(null);
    setSegments(null);
    // The segment feed first: a text document renders
    // natively from its served segments (math nodes
    // typeset by the kit's Math component). A refusal —
    // the main file is a rendered page, or the entry is
    // held by reference — falls back to the byte route's
    // page, whose own refusal is the surface if it also
    // cannot serve.
    a.entrySegments(entry.id).then(
      (seg) => {
        if (!live) return;
        if (seg.ok) {
          setSegments(seg.blocks);
          return;
        }
        a.entryPage(entry.id).then(
          (r) => {
            if (live) setPage(r);
          },
          () => {
            if (live) {
              setPage({
                ok: false,
                reason: "The page could not be fetched. Nothing was rendered.",
              });
            }
          },
        );
      },
      () => {
        if (live) {
          setPage({
            ok: false,
            reason: "The page could not be fetched. Nothing was rendered.",
          });
        }
      },
    );
    return () => {
      live = false;
    };
  }, [a, entry.id, entry.stateHash]);
  if (segments !== null) {
    return (
      <div
        className="block h-full w-full overflow-y-auto px-5 py-4"
        style={{
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-md)",
          backgroundColor: "var(--wb-surface-1)",
        }}
      >
        <SegmentBlocks blocks={segments} />
      </div>
    );
  }
  if (page === null) {
    return (
      <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
        Loading page…
      </p>
    );
  }
  if (!page.ok) {
    return (
      <p role="alert" className="text-sm" style={{ color: "var(--wb-danger)" }}>
        {page.reason}
      </p>
    );
  }
  return (
    <iframe
      title={`Rendered page of ${entry.title}`}
      sandbox="allow-scripts"
      srcDoc={page.body}
      className="block h-full w-full"
      style={{
        border: "1px solid var(--wb-border-default)",
        borderRadius: "var(--wb-radius-md)",
        backgroundColor: "var(--wb-surface-1)",
      }}
    />
  );
}

function entryFooter(e: Entry) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {e.review === "in-triage" ? <ReviewBadge kind="in-triage" text="In triage" /> : null}
      {e.review === "needs-changes" ? (
        <ReviewBadge kind="needs-changes" text={`Needs changes · ${e.reviewCount ?? 1} open`} />
      ) : null}
      {e.review === "approved" ? (
        <ReviewBadge kind="approved" text={`Approved · state ${e.stateHash ?? ""}`} />
      ) : null}
      {!e.review && e.status !== "implemented" ? <RuledChip status={e.status} /> : null}
      {e.staleNote ? <ReviewBadge kind="stale" text={e.staleNote} /> : null}
      <span
        className="inline-flex rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
        style={{ backgroundColor: "var(--wb-surface-sunken)", color: "var(--wb-content-secondary)" }}
      >
        {e.viewport} · {e.mode}
      </span>
    </span>
  );
}

type MockupFilter = "all" | "canonical" | "implemented" | "triage" | "archive";

export function Mockups() {
  useStoreVersion();
  const a = useAdapter();
  const isPhone = useIsPhone();
  const { navigate, project } = useNav();
  const [filter, setFilter] = useState<MockupFilter>("all");
  const all = a.entries(project).filter((e) => e.kind === "mockup");
  const triage = all.filter((e) => e.review === "in-triage").length;
  const shown = all.filter((e) => {
    switch (filter) {
      case "canonical":
        return e.status === "canonical";
      case "implemented":
        return e.status === "implemented";
      case "triage":
        return e.review === "in-triage";
      case "archive":
        return e.review === null && Boolean(e.staleNote);
      default:
        return true;
    }
  });

  return (
    <div className={isPhone ? "px-[18px] py-4" : "px-[26px] py-[22px]"}>
      <LargeTitle>Mockups</LargeTitle>
      <Subtitle>
        {all.length} entries · {triage} in triage
      </Subtitle>
      <div className="mb-4 flex flex-wrap gap-2">
        <PickChip label="All" on={filter === "all"} onPress={() => setFilter("all")} />
        <PickChip label="Canonical" on={filter === "canonical"} onPress={() => setFilter("canonical")} />
        <PickChip label="Implemented" on={filter === "implemented"} onPress={() => setFilter("implemented")} />
        <PickChip label="Triage only" on={filter === "triage"} onPress={() => setFilter("triage")} />
        <PickChip label="Archive" on={filter === "archive"} onPress={() => setFilter("archive")} />
      </div>
      {/* Phone goes single-column: at two columns each card
          is ~163px — titles ellipsize, the Frame footer badge
          spills past the card edge, and the specimen header
          wraps over the skeleton (mobile critic, 2026-11-15). */}
      <div className={isPhone ? "grid grid-cols-1 gap-4" : "grid grid-cols-2 gap-4"}>
        {shown.map((e) => (
          <button
            key={e.id}
            type="button"
            className="text-left"
            onClick={() => navigate({ section: "mockup", entryId: e.id })}
          >
            <Frame
              title={e.title}
              viewportLabel={`${e.viewport} · ${e.mode}`}
              archived={Boolean(e.staleNote)}
              footer={entryFooter(e)}
            >
              <div className="h-[158px]">
                <Specimen entry={e} mode={e.mode ?? "Light"} />
              </div>
            </Frame>
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
          No mockups match this filter.
        </p>
      ) : null}
    </div>
  );
}

const RULED_STATUSES: RuledStatus[] = [
  "unexplored",
  "canonical",
  "implemented",
  "deferred",
  "hard-gate",
  "abandoned",
];

const detailInputStyle: React.CSSProperties = {
  backgroundColor: "var(--wb-surface-sunken)",
  color: "var(--wb-content-primary)",
  borderRadius: 9,
  padding: "6px 10px",
  fontSize: 13.5,
};

export function MockupDetail({ entryId }: { entryId: string }) {
  useStoreVersion();
  const a = useAdapter();
  const isPhone = useIsPhone();
  const { navigate } = useNav();
  // Entry lifecycle UI state (W4) — declared before the
  // early return so the hooks order is stable.
  const [metaOpen, setMetaOpen] = useState(false);
  const [mTitle, setMTitle] = useState("");
  const [mViewport, setMViewport] = useState<"Phone" | "Desktop">("Phone");
  const [mMode, setMMode] = useState<"Light" | "Dark">("Light");
  const [filePath, setFilePath] = useState<string | null>(null);
  const [fileBody, setFileBody] = useState("");
  const [fileSha, setFileSha] = useState("");
  const [fileNote, setFileNote] = useState("");
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [supersedePick, setSupersedePick] = useState<string | null>(null);
  const [stateDraft, setStateDraft] = useState<string | null>(null);
  const [stateError, setStateError] = useState("");
  const e = a.entry(entryId);
  if (!e) {
    return (
      <div className="px-[26px] py-[22px]">
        <Subtitle>That mockup is no longer in the registry.</Subtitle>
      </div>
    );
  }
  const approved = e.review === "approved";
  const stateText = stateDraft ?? e.stateJson ?? "";

  return (
    <div className={isPhone ? "px-[18px] py-4" : "px-[26px] py-[22px]"}>
      <button
        type="button"
        onClick={() => navigate({ section: "mockups" })}
        className="mb-3 text-sm font-semibold"
        style={{ color: "var(--wb-accent)" }}
      >
        ‹ Mockups
      </button>
      {/* Phone stacks the stage + disposition over the state
          rail: the fixed 300px rail beside a flex-1 main left
          the main ~20px wide at 390px — the stage crushed and
          the Disposition label wrapped letter-by-letter
          (mobile critic, 2026-11-15). */}
      {/* Phone stack gap is 20px, the section-header
          standard: the rail's first label (State) is a
          first-child whose own margin is zeroed, so the
          stack gap IS its separation (spacing audit,
          2026-11-15). Desktop keeps the 18px gutter. */}
      <div className={isPhone ? "flex flex-col gap-[20px]" : "flex gap-[18px]"}>
        <div className="min-w-0 flex-1">
          <div className="h-[380px]">
            <EntryPageStage entry={e} />
          </div>
          <GroupLabel>Disposition</GroupLabel>
          <Group>
            <Row>
              <Lab>Approve</Lab>
              <span className="ml-auto">
                <ArmConfirm
                  label="Approve"
                  confirmLabel="Confirm approve"
                  statement={`Approve "${e.title}" at state ${e.stateHash ?? "—"} — the mockup becomes the exact spec for its build.`}
                  variant="primary"
                  disabled={approved}
                  disabledReason={approved ? "Already approved at this state." : undefined}
                  disarmKey={`${e.id}|approve|${e.stateHash}`}
                  onConfirm={() => void a.setEntryReview(e.id, "approved")}
                />
              </span>
            </Row>
            <Row>
              <Lab>Needs changes</Lab>
              <span className="ml-auto">
                <ArmConfirm
                  label="Needs changes"
                  confirmLabel="Confirm"
                  statement={`Return "${e.title}" with changes open — it stays in the review queue and the board's Review lane.`}
                  disarmKey={`${e.id}|needs|${e.reviewCount ?? 0}`}
                  onConfirm={() => void a.setEntryReview(e.id, "needs-changes")}
                />
              </span>
            </Row>
            <Row last>
              <Lab>Mark stale</Lab>
              <span className="ml-auto">
                <ArmConfirm
                  label="Mark stale"
                  confirmLabel="Confirm stale"
                  statement={`Mark "${e.title}" stale — it leaves the review queue; the entry stays registered.`}
                  variant="danger"
                  disarmKey={`${e.id}|stale`}
                  onConfirm={() => void a.setEntryReview(e.id, "stale")}
                />
              </span>
            </Row>
          </Group>
        </div>
        <div className={isPhone ? "w-full" : "w-[300px] flex-[0_0_300px]"}>
          <GroupLabel>State</GroupLabel>
          <Group>
            <Row>
              <Lab>Status</Lab>
              <span className="ml-auto">
                {e.review === "in-triage" ? (
                  <ReviewBadge kind="in-triage" text="In triage" />
                ) : e.review === "needs-changes" ? (
                  <ReviewBadge kind="needs-changes" text={`Needs changes · ${e.reviewCount ?? 1} open`} />
                ) : e.review === "approved" ? (
                  <ReviewBadge kind="approved" text="Approved" />
                ) : e.staleNote ? (
                  <ReviewBadge kind="stale" text={e.staleNote} />
                ) : (
                  <RuledChip status={e.status} />
                )}
              </span>
            </Row>
            <Row>
              <Lab>Viewport</Lab>
              <Val>{e.viewport}</Val>
            </Row>
            <Row last>
              <Lab>Mode</Lab>
              <Val>{e.mode ?? "—"}</Val>
            </Row>
          </Group>
          <GroupLabel>Approval</GroupLabel>
          <Group>
            <Row>
              <Lab>State hash</Lab>
              <Val mono>{e.stateHash ?? "—"}</Val>
            </Row>
            <Row last>
              <Lab>Approved by</Lab>
              <Val>{e.approvedBy ?? "—"}</Val>
            </Row>
          </Group>
          <GroupLabel>Review log</GroupLabel>
          <Group>
            {e.reviewLog.map((log, i) => (
              <Row key={i} last={i === e.reviewLog.length - 1}>
                <span>
                  <span className="block truncate text-[14.5px] font-medium">{log.label}</span>
                  <Sub>
                    {log.when} · {log.actor}
                  </Sub>
                </span>
              </Row>
            ))}
            {e.reviewLog.length === 0 ? (
              <Row last>
                <Lab>No review events yet</Lab>
              </Row>
            ) : null}
          </Group>
        </div>
      </div>

      <GroupLabel>Metadata</GroupLabel>
      <Group>
        <Row>
          <Lab>Title</Lab>
          <Val>{e.title}</Val>
        </Row>
        <Row>
          <Lab>Kind</Lab>
          <Val>{e.kind}</Val>
        </Row>
        <Row>
          <Lab>Registered</Lab>
          <Val>{e.registeredLabel}</Val>
        </Row>
        <Row>
          <Lab>Version</Lab>
          <Val>{e.version}</Val>
        </Row>
        <ActionRow
          label="Edit metadata…"
          onClick={() => {
            setMTitle(e.title);
            setMViewport(e.viewport ?? "Phone");
            setMMode(e.mode ?? "Light");
            setMetaOpen(true);
          }}
        />
        <Row last>
          <span className="min-w-0">
            <span className="block text-[14.5px] font-medium">Ruled status</span>
            <Sub>Set directly — the lifecycle verb behind the chip</Sub>
          </span>
          <span className="ml-auto flex max-w-[62%] flex-wrap justify-end gap-1.5">
            {RULED_STATUSES.map((s) => (
              <PickChip
                key={s}
                label={s}
                on={e.status === s}
                onPress={() => void a.setEntryStatus(e.id, s)}
              />
            ))}
          </span>
        </Row>
      </Group>

      <GroupLabel>Files · {(e.files ?? []).length}</GroupLabel>
      <Group>
        {(e.files ?? []).map((f, i) => (
          <Row key={f.path} last={i === (e.files ?? []).length - 1}>
            <span className="min-w-0">
              <span className="block truncate font-mono text-[13px]">{f.path}</span>
              <Sub>
                {f.isMain ? "Main file · " : ""}
                {f.sizeLabel ?? ""}
              </Sub>
            </span>
            <span className="ml-auto">
              <Button
                variant="secondary"
                onClick={() => {
                  setFilePath(f.path);
                  setFileNote("");
                  setFileBody("");
                  setFileSha("");
                  void a.entryFileContent(e.id, f.path).then((r) => {
                    if (r.ok) {
                      setFileBody(r.body);
                      setFileSha(r.sha);
                    } else {
                      setFileNote(r.reason);
                    }
                  });
                }}
              >
                Peek / edit
              </Button>
            </span>
          </Row>
        ))}
        {(e.files ?? []).length === 0 ? (
          <Row last>
            <Lab>No files served for this entry</Lab>
          </Row>
        ) : null}
      </Group>

      <GroupLabel>Lifecycle</GroupLabel>
      <Group>
        <ActionRow label="Verify state hash" onClick={() => void a.verifyEntry(e.id)} />
        {e.archived ? (
          <ActionRow label="Unarchive" onClick={() => void a.unarchiveEntry(e.id)} />
        ) : (
          <Row>
            <Lab>Archive entry</Lab>
            <span className="ml-auto">
              <ArmConfirm
                label="Archive"
                confirmLabel="Confirm archive"
                statement={`Archive "${e.title}" — it leaves the active registry lists; the entry and its files stay.`}
                variant="danger"
                disarmKey={`${e.id}|archive`}
                onConfirm={() => void a.archiveEntry(e.id)}
              />
            </span>
          </Row>
        )}
        <ActionRow
          label="Supersede…"
          last
          onClick={() => {
            setSupersedePick(null);
            setSupersedeOpen(true);
          }}
        />
      </Group>

      <GroupLabel>State document</GroupLabel>
      <div
        className="p-3.5"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-lg)",
        }}
      >
        <textarea
          aria-label="Entry state JSON"
          value={stateText}
          onChange={(ev) => setStateDraft(ev.target.value)}
          rows={7}
          className="w-full font-mono text-[12.5px]"
          style={{ ...detailInputStyle, resize: "vertical" }}
          placeholder="No state document served — write one to create it."
        />
        {stateError ? (
          <p role="alert" className="mt-2 mb-0 text-sm" style={{ color: "var(--wb-danger)" }}>
            {stateError}
          </p>
        ) : null}
        <div className="mt-2">
          <Button
            disabled={stateDraft === null}
            onClick={() => {
              a.setEntryState(e.id, stateText)
                .then(() => {
                  setStateDraft(null);
                  setStateError("");
                })
                .catch((err) => {
                  setStateError(err instanceof Error ? err.message : String(err));
                });
            }}
          >
            Save state
          </Button>
        </div>
      </div>

      <Sheet
        open={metaOpen}
        title="Edit metadata"
        onClose={() => setMetaOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setMetaOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!mTitle.trim()}
              onClick={() => {
                void a.setEntryMeta(e.id, { title: mTitle, viewport: mViewport, mode: mMode });
                setMetaOpen(false);
              }}
            >
              Save metadata
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Title</span>
            <input aria-label="Title" value={mTitle} onChange={(ev) => setMTitle(ev.target.value)} style={detailInputStyle} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Viewport</span>
            <select
              aria-label="Viewport"
              value={mViewport}
              onChange={(ev) => setMViewport(ev.target.value as "Phone" | "Desktop")}
              style={detailInputStyle}
            >
              <option value="Phone">Phone</option>
              <option value="Desktop">Desktop</option>
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Mode</span>
            <select
              aria-label="Mode"
              value={mMode}
              onChange={(ev) => setMMode(ev.target.value as "Light" | "Dark")}
              style={detailInputStyle}
            >
              <option value="Light">Light</option>
              <option value="Dark">Dark</option>
            </select>
          </label>
        </div>
      </Sheet>

      <Sheet
        open={filePath !== null}
        title={filePath ?? "File"}
        onClose={() => setFilePath(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setFilePath(null)}>
              Close
            </Button>
            <Button
              disabled={!fileSha}
              onClick={() => {
                if (!filePath) return;
                void a.saveEntryFile(e.id, filePath, fileBody, fileSha).then((r) => {
                  if (r.ok) {
                    setFileSha(r.sha);
                    setFileNote(`Saved · sha ${r.sha}`);
                  } else {
                    setFileNote(r.reason);
                  }
                });
              }}
            >
              Save · guarded
            </Button>
          </>
        }
      >
        {fileNote ? (
          <p role="alert" className="mb-3 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            {fileNote}
          </p>
        ) : null}
        <p className="mb-2 text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
          Opened at sha <span className="font-mono">{fileSha || "…"}</span> — the save refuses if
          the file moved since.
        </p>
        <textarea
          aria-label="File content"
          value={fileBody}
          onChange={(ev) => setFileBody(ev.target.value)}
          rows={14}
          className="w-full font-mono text-[12.5px]"
          style={{ ...detailInputStyle, resize: "vertical" }}
        />
      </Sheet>

      <Sheet
        open={supersedeOpen}
        title="Supersede with…"
        onClose={() => setSupersedeOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSupersedeOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={!supersedePick}
              onClick={() => {
                if (supersedePick) void a.supersedeEntry(e.id, supersedePick);
                setSupersedeOpen(false);
              }}
            >
              Confirm supersede
            </Button>
          </>
        }
      >
        <Group>
          {a
            .entries(e.project)
            .filter((x) => x.id !== e.id)
            .map((x, i, arr) => (
              <Row
                key={x.id}
                last={i === arr.length - 1}
                selected={supersedePick === x.id}
                onClick={() => setSupersedePick(x.id)}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[14.5px] font-medium">{x.title}</span>
                  <Sub>
                    {x.kind} · {x.status}
                  </Sub>
                </span>
              </Row>
            ))}
        </Group>
      </Sheet>
    </div>
  );
}
