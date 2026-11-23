import { useEffect, useState } from "react";
import { SegmentedControl } from "@kit/components/controls/SegmentedControl";
import { DatasetView } from "./DatasetView";
import { Toggle } from "@kit/components/controls/Toggle";
import { ChevronDown, ChevronLeft, ChevronRight, File, FileSpreadsheet, FileText, Folder } from "lucide-react";
import { useIsPhone } from "@kit/lib/responsive";
import { lineDiff } from "../components/ui";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { RepoFile } from "../lib/types";
import {
  ActionRow,
  Group,
  GroupLabel,
  Lab,
  Row,
  Sub,
  TOGGLE_LABEL_SR_ONLY,
  Val,
} from "../components/ui";

// Frames 15–20 · Explorer + peek. One surface at two widths:
// phone renders the explorer (folders push, files open the
// peek); desktop renders the split view (TreeRail + peek
// pane). Withheld (secret-shaped) files never render content
// until the reveal dialog's verdict — and the reveal is
// dropped when you leave the file (frame 19).

export function findInTree(files: RepoFile[], path: string): RepoFile | undefined {
  let level: RepoFile[] | undefined = files;
  let found: RepoFile | undefined;
  for (const part of path.split("/")) {
    found = level?.find((f) => f.name === part);
    if (!found) return undefined;
    level = found.children;
  }
  return found;
}

function folderAt(files: RepoFile[], trail: string[]): RepoFile[] {
  let level = files;
  for (const part of trail) {
    const next = level.find((f) => f.name === part && f.kind === "folder");
    if (!next?.children) return [];
    level = next.children;
  }
  return level;
}

function FileGlyph({ file, size = 18 }: { file: RepoFile; size?: number }) {
  if (file.kind === "folder") {
    return <Folder size={size} style={{ color: "var(--wb-okabe-orange)", opacity: file.classification === "pruned" ? 0.45 : 1 }} />;
  }
  if (file.dataset) return <FileSpreadsheet size={size} style={{ color: "var(--wb-content-secondary)" }} />;
  if (file.name.endsWith(".md")) return <FileText size={size} style={{ color: "var(--wb-content-secondary)" }} />;
  return <File size={size} style={{ color: "var(--wb-content-secondary)" }} />;
}

function ClassChip({ file }: { file: RepoFile }) {
  if (!file.classification) return null;
  const label =
    file.classification === "untracked" ? "Untracked" : file.classification === "pruned" ? "Pruned" : "Withheld";
  return (
    <span
      className="ml-auto inline-flex shrink-0 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
      style={{ backgroundColor: "var(--wb-surface-sunken)", color: "var(--wb-content-secondary)" }}
    >
      {label}
    </span>
  );
}

/** Frame 19 — the reveal dialog: Dialog over Scrim, naming
 *  the action, the item, and the consequence. */
export function RevealDialog({
  fileName,
  onKeep,
  onReveal,
}: {
  fileName: string;
  onKeep: () => void;
  onReveal: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: "rgb(16 18 10 / 0.45)" }}
      role="dialog"
      aria-modal="true"
      aria-label={`Reveal ${fileName}?`}
    >
      <div
        className="w-[400px] max-w-[calc(100vw-32px)] p-[22px]"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          borderRadius: 16,
          boxShadow: "0 18px 50px rgb(0 0 0 / 0.4)",
          color: "var(--wb-content-primary)",
        }}
      >
        <div className="mb-1.5 text-lg font-bold [overflow-wrap:anywhere]">Reveal {fileName}?</div>
        <p className="mb-4 text-sm leading-[1.45]" style={{ color: "var(--wb-content-secondary)" }}>
          The file is secret-shaped, so its content is withheld. Revealing shows it for this file
          only — it is never cached, and it is dropped when you leave the file.
        </p>
        <Group>
          <ActionRow label="Keep withheld" onClick={onKeep} />
          <ActionRow label="Reveal" danger onClick={onReveal} last />
        </Group>
      </div>
    </div>
  );
}

function DiffView({ file }: { file: RepoFile }) {
  const diff = lineDiff(file.headContent ?? "", file.content ?? "");
  const adds = diff.filter((d) => d.kind === "add").length;
  const dels = diff.filter((d) => d.kind === "del").length;
  // Trim to the changed region with one context line around.
  const firstChange = diff.findIndex((d) => d.kind !== "ctx");
  const lastChange = diff.length - 1 - [...diff].reverse().findIndex((d) => d.kind !== "ctx");
  const shown = firstChange === -1 ? diff : diff.slice(Math.max(0, firstChange - 1), lastChange + 2);
  return (
    <>
      <div
        className="overflow-x-auto p-4 font-mono text-xs leading-[1.9]"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-lg)",
          whiteSpace: "pre",
        }}
      >
        <div style={{ color: "var(--wb-content-muted)" }}>
          @@ −{Math.max(1, firstChange)},4 +{Math.max(1, firstChange)},5 @@
        </div>
        {shown.map((d, i) => (
          <div
            key={i}
            style={{
              backgroundColor:
                d.kind === "add"
                  ? "color-mix(in srgb, var(--wb-okabe-bluish-green) 16%, transparent)"
                  : d.kind === "del"
                    ? "color-mix(in srgb, var(--wb-okabe-vermilion) 14%, transparent)"
                    : undefined,
              borderRadius: 4,
              padding: "0 4px",
            }}
          >
            {d.kind === "add" ? "+ " : d.kind === "del" ? "- " : "  "}
            {d.text}
          </div>
        ))}
      </div>
      <GroupLabel>Diff</GroupLabel>
      <Group>
        <Row>
          <Lab>Against</Lab>
          <Val mono>HEAD · main</Val>
        </Row>
        <Row last>
          <Lab>Changed</Lab>
          <Val>
            +{adds} · −{dels} lines
          </Val>
        </Row>
      </Group>
    </>
  );
}

function FileFacts({ file }: { file: RepoFile }) {
  return (
    <>
      <GroupLabel>File</GroupLabel>
      <Group>
        <Row>
          <Lab>Size</Lab>
          <Val>{file.sizeLabel ?? "—"}</Val>
        </Row>
        <Row>
          <Lab>Sha</Lab>
          <Val mono>{file.sha ?? "—"}</Val>
        </Row>
        <Row>
          <Lab>Kind</Lab>
          {file.classification === "withheld" ? (
            <span
              className="ml-auto inline-flex shrink-0 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
              style={{ backgroundColor: "var(--wb-surface-sunken)", color: "var(--wb-content-secondary)" }}
            >
              Withheld · secret-shaped
            </span>
          ) : (
            <span
              className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
              style={{
                backgroundColor: "color-mix(in srgb, var(--wb-okabe-bluish-green) 14%, transparent)",
                color: "var(--wb-status-implemented-text)",
              }}
            >
              <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: "var(--wb-okabe-bluish-green)" }} />
              Tracked
            </span>
          )}
        </Row>
        <Row last>
          <Lab>Editable</Lab>
          <Val>{file.editable === "guarded" ? "Guarded save" : (file.editableNote ?? "No")}</Val>
        </Row>
      </Group>
    </>
  );
}

/** The peek pane — shared by the phone peek (frames 17–18)
 *  and the desktop split view (frame 20). */
export function PeekPane({
  repoSlug,
  path,
  initialTab,
}: {
  repoSlug: string;
  path: string;
  initialTab?: "content" | "diff" | "table";
}) {
  useStoreVersion();
  const a = useAdapter();
  const { navigate } = useNav();
  const repo = a.repo(repoSlug);
  const file = repo ? findInTree(repo.files, path) : undefined;
  const hasDiff = Boolean(file?.headContent && file.headContent !== file.content);
  const defaultTab = file?.dataset ? "table" : hasDiff && initialTab === "diff" ? "diff" : file?.dataset ? "table" : "content";
  const [tab, setTab] = useState<"content" | "diff" | "table">(initialTab ?? defaultTab);
  const [revealOpen, setRevealOpen] = useState(false);
  const [revealed, setRevealed] = useState(false);
  // Leaving the file drops the reveal (frame 19's rule).
  useEffect(() => {
    setRevealed(false);
    setRevealOpen(false);
    setTab(initialTab ?? defaultTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, repoSlug]);

  if (!repo || !file || file.kind !== "file") {
    return (
      <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
        That file is not in the served tree.
      </p>
    );
  }
  const withheld = file.classification === "withheld" && !revealed;
  const tabs: { value: "content" | "diff" | "table"; label: string }[] = file.dataset
    ? [
        { value: "content", label: "Content" },
        { value: "table", label: "Table" },
        ...(hasDiff ? [{ value: "diff" as const, label: "Diff" }] : []),
      ]
    : [
        { value: "content", label: "Content" },
        ...(hasDiff ? [{ value: "diff" as const, label: "Diff" }] : []),
      ];

  return (
    <div>
      <div className="mb-3.5 flex flex-wrap items-center gap-3.5">
        <h2 className="m-0 min-w-0 text-2xl font-bold [overflow-wrap:anywhere]">{file.name}</h2>
        {/* The segmented control must not be squeezed by the
            pill beside it: flex-squeezed below two-pill width
            it wraps its pills into a tall stacked track
            (mobile critic). flex-none keeps the
            control whole; the pill wraps instead. */}
        <span className="ml-auto flex flex-wrap items-center gap-2.5 [&_fieldset]:flex-none">
          <SegmentedControl
            ariaLabel="Peek view"
            options={tabs}
            value={tab}
            onChange={(v) => setTab(v)}
          />
          {file.editable !== "guarded" ? (
            <span
              className="rounded-full px-3 py-1 text-xs font-semibold"
              style={{
                backgroundColor: "var(--wb-surface-2)",
                border: "1px solid var(--wb-border-strong)",
                color: "var(--wb-content-secondary)",
              }}
            >
              Edit unavailable · {file.dataset ? "binary dataset" : "not editable"}
            </span>
          ) : null}
        </span>
      </div>

      {withheld ? (
        <>
          <div
            className="p-5 text-sm leading-[1.6]"
            style={{
              backgroundColor: "var(--wb-surface-2)",
              border: "1px solid var(--wb-border-default)",
              borderRadius: "var(--wb-radius-lg)",
              color: "var(--wb-content-secondary)",
            }}
          >
            Content withheld — this file is secret-shaped. Its facts are served; its content is
            not, until you reveal it.
          </div>
          <div className="mt-4">
            <Group>
              <ActionRow label="Reveal file…" onClick={() => setRevealOpen(true)} last />
            </Group>
          </div>
        </>
      ) : tab === "diff" && hasDiff ? (
        <DiffView file={file} />
      ) : tab === "table" && file.dataset ? (
        <DatasetView repoSlug={repoSlug} path={path} file={file} />
      ) : (
        <div
          className="overflow-x-auto p-4 font-mono text-xs leading-[1.7]"
          style={{
            backgroundColor: "var(--wb-surface-2)",
            border: "1px solid var(--wb-border-default)",
            borderRadius: "var(--wb-radius-lg)",
            whiteSpace: "pre",
          }}
        >
          {file.content ?? "(no content served for this file)"}
        </div>
      )}

      <FileFacts file={file} />
      {file.editable === "guarded" ? (
        <div className="mt-4">
          <Group>
            <ActionRow
              label="Edit file"
              onClick={() => navigate({ section: "editor", repo: repoSlug, path })}
              last
            />
          </Group>
        </div>
      ) : null}

      {revealOpen ? (
        <RevealDialog
          fileName={file.name}
          onKeep={() => setRevealOpen(false)}
          onReveal={() => {
            setRevealOpen(false);
            setRevealed(true);
          }}
        />
      ) : null}
    </div>
  );
}

/** Phone chrome for frames 15–18. */
function PhoneShell({
  backLabel,
  onBack,
  children,
}: {
  backLabel: string;
  onBack: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex h-full w-full max-w-[430px] flex-col" style={{ backgroundColor: "var(--wb-surface-canvas)" }}>
      <div className="flex items-center justify-between px-[30px] pt-4 pb-0.5 text-[14.5px] font-semibold">
        <span>9:41</span>
        <span className="flex items-center gap-1.5" aria-hidden>
          <span className="flex items-end gap-[3px]">
            {[4, 6, 8.5, 11].map((h, i) => (
              <span key={i} className="block w-[3px] rounded-[1px]" style={{ height: h, backgroundColor: "var(--wb-content-primary)", opacity: i === 3 ? 0.35 : 1 }} />
            ))}
          </span>
          <span className="block h-[12px] w-[25px] rounded-[3.5px]" style={{ border: "1px solid var(--wb-content-muted)" }}>
            <span className="m-[2px] block h-[7px] w-[13px] rounded-[1.8px]" style={{ backgroundColor: "var(--wb-content-primary)" }} />
          </span>
        </span>
      </div>
      <button
        type="button"
        onClick={onBack}
        className="flex min-h-[44px] items-center gap-1.5 px-[18px] pt-2.5 pb-1 text-left text-[16.5px] font-medium"
        style={{ color: "var(--wb-accent)" }}
      >
        <ChevronLeft size={16} className="shrink-0" /> <span className="min-w-0 truncate">{backLabel}</span>
      </button>
      <div className="min-h-0 flex-1 overflow-y-auto px-[18px] pt-2.5 pb-3.5">{children}</div>
      <div className="mx-auto mt-1.5 mb-2 h-[5px] w-[134px] rounded-[3px]" style={{ backgroundColor: "var(--wb-content-primary)", opacity: 0.85 }} />
    </div>
  );
}

/** Frames 15–16 · the phone explorer. */
export function PhoneExplorer({ repoSlug, trail }: { repoSlug: string; trail: string[] }) {
  useStoreVersion();
  const a = useAdapter();
  const { navigate } = useNav();
  const [showHidden, setShowHidden] = useState(false);
  const repo = a.repo(repoSlug);
  if (!repo) return null;
  const items = folderAt(repo.files, trail).filter(
    (f) => showHidden || (!f.hidden && f.classification !== "withheld"),
  );
  const folders = items.filter((f) => f.kind === "folder");
  const files = items.filter((f) => f.kind === "file");
  const title = trail.length > 0 ? trail[trail.length - 1] : repo.name;
  const backLabel = trail.length > 1 ? trail[trail.length - 2] : trail.length === 1 ? repo.name : "Code";
  const onBack = () => {
    if (trail.length > 0) navigate({ section: "browse", repo: repoSlug, path: trail.slice(0, -1) });
    else navigate({ section: "code" });
  };

  return (
    <PhoneShell backLabel={backLabel} onBack={onBack}>
      <h2 className="m-0 mb-1 text-[30px] font-bold [overflow-wrap:anywhere]">{title}</h2>
      {trail.length === 0 ? (
        <div className="my-2 mb-4">
          <SegmentedControl
            ariaLabel="Repo view"
            options={[
              { value: "status", label: "Status" },
              { value: "files", label: "Files" },
              { value: "history", label: "History" },
            ]}
            value="files"
            onChange={(v) => {
              if (v !== "files") navigate({ section: "repo", repo: repoSlug });
            }}
          />
        </div>
      ) : (
        <p className="mt-0 mb-3.5 text-sm [overflow-wrap:anywhere]" style={{ color: "var(--wb-content-secondary)" }}>
          {repo.name} / {trail.join(" / ")}
        </p>
      )}
      {folders.length > 0 ? (
        <>
          <GroupLabel>Folders</GroupLabel>
          <Group>
            {folders.map((f, i) => (
              <Row
                key={f.name}
                last={i === folders.length - 1}
                onClick={() => navigate({ section: "browse", repo: repoSlug, path: [...trail, f.name] })}
              >
                <FileGlyph file={f} size={20} />
                <Lab>{f.name}</Lab>
                {f.classification === "pruned" ? <ClassChip file={f} /> : <span className="ml-auto" />}
                <ChevronRight size={15} style={{ color: "var(--wb-content-muted)" }} />
              </Row>
            ))}
          </Group>
        </>
      ) : null}
      {files.length > 0 ? (
        <>
          <GroupLabel>Files</GroupLabel>
          <Group>
            {files.map((f, i) => (
              <Row
                key={f.name}
                last={i === files.length - 1}
                onClick={() =>
                  navigate({ section: "peek", repo: repoSlug, path: [...trail, f.name].join("/") })
                }
              >
                <FileGlyph file={f} />
                <Lab>{f.name}</Lab>
                <ClassChip file={f} />
                <ChevronRight size={15} style={{ color: "var(--wb-content-muted)" }} />
              </Row>
            ))}
          </Group>
        </>
      ) : null}
      <div className="mt-4">
        <Group>
          <Row last>
            <Lab>Show hidden &amp; ignored</Lab>
            <span className="ml-auto">
              <Toggle checked={showHidden} onChange={setShowHidden} label="Show hidden and ignored" className={TOGGLE_LABEL_SR_ONLY} />
            </span>
          </Row>
        </Group>
      </div>
    </PhoneShell>
  );
}

/** Frames 17–18 · the phone peek. */
export function PhonePeek({ repoSlug, path }: { repoSlug: string; path: string }) {
  const a = useAdapter();
  const { navigate } = useNav();
  const repo = a.repo(repoSlug);
  const parts = path.split("/");
  const parent = parts.slice(0, -1);
  const file = repo ? findInTree(repo.files, path) : undefined;
  const hasDiff = Boolean(file?.headContent && file.headContent !== file.content);
  return (
    <PhoneShell
      backLabel={parent.length > 0 ? parent[parent.length - 1] : repo?.name ?? "Code"}
      onBack={() => navigate({ section: "browse", repo: repoSlug, path: parent })}
    >
      <PeekPane repoSlug={repoSlug} path={path} initialTab={hasDiff ? "content" : undefined} />
    </PhoneShell>
  );
}

/** Frame 20 · the desktop split view: TreeRail + peek pane. */
export function SplitView({
  repoSlug,
  initialPath,
}: {
  repoSlug: string;
  initialPath?: string;
}) {
  useStoreVersion();
  const a = useAdapter();
  const { navigate } = useNav();
  const repo = a.repo(repoSlug);
  const [selected, setSelected] = useState<string>(
    initialPath ?? (repoSlug === "aldercrest" ? "data/records.csv" : ""),
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["data"]));
  const [showHidden, setShowHidden] = useState(false);
  useEffect(() => {
    if (initialPath) setSelected(initialPath);
  }, [initialPath]);
  if (!repo) return null;

  const renderTree = (files: RepoFile[], prefix: string, depth: number): React.ReactNode =>
    files
      .filter((f) => showHidden || (!f.hidden && f.classification !== "withheld"))
      .map((f) => {
        const p = prefix ? `${prefix}/${f.name}` : f.name;
        if (f.kind === "folder") {
          const open = expanded.has(p);
          return (
            <div key={p}>
              <button
                type="button"
                onClick={() =>
                  setExpanded((prev) => {
                    const next = new Set(prev);
                    if (next.has(p)) next.delete(p);
                    else next.add(p);
                    return next;
                  })
                }
                className="flex w-full items-center gap-2 rounded-[9px] px-2.5 py-[7px] text-left text-sm"
                style={{ paddingLeft: 10 + depth * 14, color: "var(--wb-content-primary)" }}
              >
                {open ? <ChevronDown size={15} className="shrink-0" /> : <ChevronRight size={15} className="shrink-0" />}
                <FileGlyph file={f} size={18} />
                <span className="min-w-0 truncate">{f.name}</span>
                {f.classification === "pruned" ? <ClassChip file={f} /> : null}
              </button>
              {open && f.children ? renderTree(f.children, p, depth + 1) : null}
            </div>
          );
        }
        return (
          <button
            key={p}
            type="button"
            onClick={() => setSelected(p)}
            className="flex w-full items-center gap-2 rounded-[9px] px-2.5 py-[7px] text-left text-sm"
            style={{
              paddingLeft: 10 + depth * 14 + 16,
              backgroundColor: selected === p ? "var(--wb-highlight-selection-fill)" : undefined,
              fontWeight: selected === p ? 600 : 400,
              color: "var(--wb-content-primary)",
            }}
          >
            <FileGlyph file={f} size={16} />
            <span className="min-w-0 truncate">{f.name}</span>
            <ClassChip file={f} />
          </button>
        );
      });

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex h-[52px] flex-[0_0_52px] items-center gap-3.5 px-[22px]"
        style={{ backgroundColor: "var(--wb-surface-1)", borderBottom: "1px solid var(--wb-border-default)" }}
      >
        <button
          type="button"
          onClick={() => navigate({ section: "code" })}
          className="shrink-0 text-sm font-semibold"
          style={{ color: "var(--wb-accent)" }}
        >
          ‹ Code
        </button>
        <span className="min-w-0 flex-1 truncate text-[13.5px]" style={{ color: "var(--wb-content-secondary)" }}>
          / {repo.name} / <b style={{ color: "var(--wb-content-primary)" }}>Files</b>
        </span>
        <span className="ml-auto">
          <SegmentedControl
            ariaLabel="Repo view"
            options={[
              { value: "status", label: "Status" },
              { value: "files", label: "Files" },
              { value: "history", label: "History" },
            ]}
            value="files"
            onChange={(v) => {
              if (v !== "files") navigate({ section: "repo", repo: repoSlug });
            }}
          />
        </span>
      </div>
      <div className="flex min-h-0 flex-1">
        <div
          className="flex w-[296px] flex-[0_0_296px] flex-col gap-0.5 overflow-y-auto px-3 py-4"
          style={{ backgroundColor: "var(--wb-surface-2)", borderRight: "1px solid var(--wb-border-default)" }}
        >
          <div
            className="px-2.5 pt-0.5 pb-2 text-xs font-bold tracking-[0.07em] uppercase"
            style={{ color: "var(--wb-content-muted)" }}
          >
            {repo.name}
          </div>
          {renderTree(repo.files, "", 0)}
          <div className="mt-auto pt-2.5" style={{ borderTop: "1px solid var(--wb-border-default)" }}>
            <div className="flex items-center justify-between px-2.5 py-[7px] text-sm">
              <span>Show hidden &amp; ignored</span>
              <Toggle checked={showHidden} onChange={setShowHidden} label="Show hidden and ignored" className={TOGGLE_LABEL_SR_ONLY} />
            </div>
          </div>
        </div>
        <div className="min-w-0 flex-1 overflow-y-auto px-[26px] py-5">
          {selected ? (
            <PeekPane key={selected} repoSlug={repoSlug} path={selected} />
          ) : (
            <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              Select a file in the tree to peek at it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Browse target: phone explorer or desktop split view. */
export function Browse({ repoSlug, trail }: { repoSlug: string; trail: string[] }) {
  const isPhone = useIsPhone();
  if (isPhone) return <PhoneExplorer repoSlug={repoSlug} trail={trail} />;
  return <SplitView repoSlug={repoSlug} />;
}

/** Peek target: phone peek or desktop split view on the file. */
export function PeekPage({ repoSlug, path }: { repoSlug: string; path: string }) {
  const isPhone = useIsPhone();
  if (isPhone) return <PhonePeek repoSlug={repoSlug} path={path} />;
  return <SplitView repoSlug={repoSlug} initialPath={path} />;
}
