// The diff + anchor derivations both adapters share (the
// arming.ts pattern: one pure model, two stores). The diff
// model computes over the seam's RepoFile snapshots — HEAD
// content vs staged vs working content — and normalizes
// the pipeline's served /diff payload (files → hunks →
// lines) into the same ProjectDiff shape.

import { lineDiff } from "./lineDiff";
import type {
  AnnotationThread,
  DiffFile,
  DiffMode,
  PlanQuestion,
  ProjectDiff,
  RepoFile,
} from "./types";

export function flattenRepoFiles(
  files: RepoFile[],
  prefix = "",
): { path: string; file: RepoFile }[] {
  const out: { path: string; file: RepoFile }[] = [];
  for (const f of files) {
    const path = prefix ? `${prefix}/${f.name}` : f.name;
    if (f.kind === "folder") out.push(...flattenRepoFiles(f.children ?? [], path));
    else out.push({ path, file: f });
  }
  return out;
}

function toDiffFile(
  path: string,
  lines: { kind: "ctx" | "add" | "del"; text: string }[],
): DiffFile {
  return {
    path,
    adds: lines.filter((l) => l.kind === "add").length,
    dels: lines.filter((l) => l.kind === "del").length,
    lines,
  };
}

const MODE_LABELS: Record<DiffMode, string> = {
  working: "Working tree vs HEAD",
  uncommitted: "Uncommitted — staged / unstaged split",
  committed: "Committed",
  range: "Range",
};

/** Compute a project's diff from the store's file
 *  snapshots. Modes the snapshots cannot answer (committed,
 *  range — no per-commit content is served into the store)
 *  return an honest note, never a fabricated diff. */
export function computeDiff(
  files: RepoFile[],
  mode: DiffMode,
): ProjectDiff {
  const flat = flattenRepoFiles(files);
  if (mode === "working") {
    const out: DiffFile[] = [];
    for (const { path, file } of flat) {
      if (file.headContent !== undefined && file.headContent !== (file.content ?? "")) {
        out.push(toDiffFile(path, lineDiff(file.headContent, file.content ?? "")));
      }
    }
    return { mode, label: MODE_LABELS[mode], files: out };
  }
  if (mode === "uncommitted") {
    const staged: DiffFile[] = [];
    const unstaged: DiffFile[] = [];
    for (const { path, file } of flat) {
      const head = file.headContent ?? file.content ?? "";
      const index = file.stagedContent ?? head;
      const work = file.content ?? "";
      if (index !== head) staged.push(toDiffFile(path, lineDiff(head, index)));
      if (work !== index) unstaged.push(toDiffFile(path, lineDiff(index, work)));
    }
    return { mode, label: MODE_LABELS[mode], files: [], staged, unstaged };
  }
  return {
    mode,
    label: MODE_LABELS[mode],
    files: [],
    note: "This store serves no per-commit snapshots — committed and range diffs ride the live /diff feed at the serving shell.",
  };
}

/** Normalize the pipeline's served diff payload (the
 *  feeds document's per-project `diff`) into ProjectDiff.
 *  Returns null when the payload is an error or carries
 *  no file list. */
export function normalizeServedDiff(
  payload: unknown,
  mode: DiffMode,
): ProjectDiff | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as {
    files?: unknown;
    note?: string;
    error?: string;
    mode?: string;
  };
  if (p.error || !Array.isArray(p.files)) return null;
  const files: DiffFile[] = [];
  for (const raw of p.files) {
    const f = raw as {
      path?: string;
      hunks?: { lines?: { kind?: string; text?: string }[] }[];
    };
    if (!f.path) continue;
    const lines: DiffFile["lines"] = [];
    for (const hunk of f.hunks ?? []) {
      for (const line of hunk.lines ?? []) {
        if (line.kind === "add" || line.kind === "del") {
          lines.push({ kind: line.kind, text: line.text ?? "" });
        } else if (line.kind === "context") {
          lines.push({ kind: "ctx", text: line.text ?? "" });
        }
      }
    }
    files.push(toDiffFile(f.path, lines));
  }
  return {
    mode,
    label: MODE_LABELS[mode],
    files,
    note: typeof p.note === "string" ? p.note : undefined,
  };
}

/** Parse a plan file's `## Questions` section (SPEC §5.1:
 *  questions live in the plan file as checklist lines —
 *  `- [ ] q1: text` open, `- [x] q1: text — answer`
 *  answered). The live adapter projects plan questions
 *  from the served markdown with this; the mock seeds the
 *  same shape directly. */
export function parsePlanQuestions(raw: string): PlanQuestion[] {
  const out: PlanQuestion[] = [];
  let inSection = false;
  for (const line of raw.split("\n")) {
    if (/^##\s+/.test(line)) {
      inSection = /^##\s+Questions\b/i.test(line);
      continue;
    }
    if (!inSection) continue;
    const m = /^- \[([ xX])\]\s+(\S+):\s+(.*)$/.exec(line);
    if (!m) continue;
    const answered = m[1].toLowerCase() === "x";
    const rest = m[3];
    const split = rest.split(" — ");
    out.push({
      id: m[2],
      text: answered && split.length > 1 ? split.slice(0, -1).join(" — ") : rest,
      answer: answered && split.length > 1 ? split[split.length - 1] : undefined,
      answeredBy: answered ? "plan file" : undefined,
      answeredLabel: answered ? "in the plan" : undefined,
    });
  }
  return out;
}

/** Write answers back into the plan file's Questions
 *  section — the client mirror of the backend's
 *  apply_answers: the open line becomes a checked line
 *  carrying the answer. */
export function applyAnswersToRaw(
  raw: string,
  answers: Record<string, string>,
): string {
  return raw
    .split("\n")
    .map((line) => {
      const m = /^- \[ \]\s+(\S+):\s+(.*)$/.exec(line);
      if (m && answers[m[1]]?.trim()) {
        return `- [x] ${m[1]}: ${m[2]} — ${answers[m[1]].trim()}`;
      }
      return line;
    })
    .join("\n");
}

/** Relocation derivation for one annotation thread against
 *  the plan's current text: the quote's line intact →
 *  anchored; the quote found in a changed line →
 *  relocated; the quote gone → orphaned. */
export function anchorStatus(
  raw: string,
  quote: string,
  context: string | undefined,
): AnnotationThread["status"] {
  const lines = raw.split("\n");
  const line = lines.find((l) => l.includes(quote));
  if (line === undefined) return "orphaned";
  if (context !== undefined && line !== context) return "relocated";
  return "anchored";
}
