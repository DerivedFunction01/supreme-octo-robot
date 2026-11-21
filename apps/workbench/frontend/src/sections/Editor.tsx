import { useEffect, useRef, useState } from "react";
import { Button } from "@kit/components/controls/Button";
import { DegradedBanner } from "@kit/components/display/DegradedBanner";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import { findInTree } from "./Explorer";
import { Group, GroupLabel, Lab, Row, Val } from "../components/ui";

// Frames 12–13 · File editor — the DocumentSurface: one
// surface, mono body, save state in the header, file facts
// below. Saves are guarded: sha compare-and-swap through the
// adapter — a stale sha refuses, and the config gate
// (Settings → Guarded file saves) answers first. Leaving with
// unsaved edits raises the discard guard (frame 13), which
// App renders.

export function Editor({ repoSlug, path }: { repoSlug: string; path: string }) {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, setEditorGuard } = useNav();
  const repo = a.repo(repoSlug);
  const file = repo ? findInTree(repo.files, path) : undefined;

  const [draft, setDraft] = useState<string | null>(null);
  const [baseSha, setBaseSha] = useState<string>("");
  const [savedLabel, setSavedLabel] = useState<string>("Yesterday · 6:42 PM");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const draftRef = useRef<string>("");
  const baseShaRef = useRef<string>("");

  // Open the file: the draft starts at the served content,
  // pinned to the served sha. A file whose peek the feeds
  // document deferred carries no content yet — its open
  // rides the adapter's on-demand file route, and the
  // draft waits for the served content + sha.
  useEffect(() => {
    if (file && draft === null) {
      if (file.content !== undefined) {
        setDraft(file.content);
        draftRef.current = file.content;
        setBaseSha(file.sha ?? "");
        baseShaRef.current = file.sha ?? "";
      } else {
        let live = true;
        a.repoFileContent(repoSlug, path).then((r) => {
          if (!live) return;
          if (r.ok) {
            setDraft(r.body);
            draftRef.current = r.body;
            setBaseSha(r.sha);
            baseShaRef.current = r.sha;
          } else {
            setError(r.reason);
            setDraft("");
            draftRef.current = "";
          }
        });
        return () => {
          live = false;
        };
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  const dirty = draft !== null && file !== undefined && draft !== (file.content ?? "");

  const doSave = async () => {
    const result = await a.guardedSave(repoSlug, path, draftRef.current, baseShaRef.current);
    if (result.ok) {
      setBaseSha(result.sha);
      baseShaRef.current = result.sha;
      setSavedLabel(result.savedLabel);
      setError(null);
      setNotice(null);
    } else {
      setError(result.reason);
    }
    return result;
  };

  // Register the discard guard while the draft is dirty.
  useEffect(() => {
    if (dirty && file) {
      setEditorGuard({
        fileName: file.name,
        sha: baseShaRef.current,
        save: doSave,
        discard: () => {
          setDraft(file.content ?? "");
          draftRef.current = file.content ?? "";
        },
      });
    } else {
      setEditorGuard(null);
    }
    return () => setEditorGuard(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, file?.name]);

  if (!repo || !file) {
    return (
      <div className="px-[26px] py-[22px]">
        <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
          That file is not in the served tree.
        </p>
      </div>
    );
  }
  const editingOn = a.settings().guardedSaves;

  return (
    <div className="px-[26px] py-[22px]">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => navigate({ section: "browse", repo: repoSlug, path: path.split("/").slice(0, -1) })}
          className="shrink-0 text-sm font-semibold"
          style={{ color: "var(--wb-accent)" }}
        >
          ‹ Files
        </button>
        <span className="min-w-0 flex-1 truncate text-[13.5px]" style={{ color: "var(--wb-content-secondary)" }}>
          {repo.name} / <b style={{ color: "var(--wb-content-primary)" }}>{file.name}</b>
        </span>
        <span className="ml-auto flex items-center gap-2">
          {dirty ? (
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
              style={{
                backgroundColor: "color-mix(in srgb, var(--wb-okabe-orange) 16%, transparent)",
                color: "var(--wb-status-stale-text)",
              }}
            >
              <span className="block h-[7px] w-[7px] rounded-full" style={{ backgroundColor: "var(--wb-okabe-orange)" }} />
              Edited · unsaved
            </span>
          ) : null}
          <Button variant="primary" disabled={!dirty} onClick={doSave}>
            Save
          </Button>
        </span>
      </div>

      {!editingOn ? (
        <div className="mb-4">
          <DegradedBanner
            message="Editing is off for this viewer."
            detail="Guarded file saves are config-gated and default off — enable them in Settings → Workbench, and Save will answer."
          />
        </div>
      ) : null}
      {error ? (
        <div className="mb-4">
          <DegradedBanner tone="source-format" message={error} />
        </div>
      ) : null}
      {notice ? (
        <div className="mb-4">
          <DegradedBanner message={notice} />
        </div>
      ) : null}

      <textarea
        aria-label={`Edit ${file.name}`}
        value={draft ?? ""}
        onChange={(e) => {
          setDraft(e.target.value);
          draftRef.current = e.target.value;
          setError(null);
        }}
        rows={16}
        spellCheck={false}
        className="w-full p-5 font-mono text-[13px] leading-[1.75]"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-lg)",
          color: "var(--wb-content-primary)",
          outline: "none",
        }}
      />

      <GroupLabel>File</GroupLabel>
      <Group>
        <Row>
          <Lab>Sha</Lab>
          <Val mono>
            {baseSha} → {dirty ? "edited" : baseSha}
          </Val>
        </Row>
        <Row>
          <Lab>Guarded save</Lab>
          <Val>Compare-and-swap · a stale sha refuses</Val>
        </Row>
        <Row last>
          <Lab>Last saved</Lab>
          <Val>{savedLabel}</Val>
        </Row>
      </Group>
    </div>
  );
}
