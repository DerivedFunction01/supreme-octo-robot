// The live adapter's shared context: the projected state
// (state.ts) plus the transport and read services the
// adapter class itself owns. The feature modules under
// liveAdapter/ are plain functions over this context; the
// class in liveAdapter.ts builds it and delegates.

import type { FeedBoard, WorkbenchFeeds } from "../feeds";
import type { BoardCard } from "../seam";
import type { WbChannel } from "../transport";
import type {
  AnnotationThread,
  AppSettings,
  ArmedRow,
  Entry,
  FileTodo,
  GoalRecord,
  InboxMessage,
  MessageThread,
  Plan,
  ProgressDerivation,
  Project,
  Repo,
  ServerCare,
} from "../types";

export interface LiveState {
  projectList: Project[];
  entryList: Entry[];
  planList: Plan[];
  todoList: FileTodo[];
  messageList: InboxMessage[];
  repoList: Repo[];
  goalList: GoalRecord[];
  boards: Map<string, FeedBoard>;
  /** Each entry's main file, as served in its detail's
   *  file list — the byte route's path for the page. */
  pagePaths: Map<string, string>;
  /** Served classification blocks per project+todo. */
  servedDerivations: Map<string, ProgressDerivation>;
  /** Todos mutated locally since the snapshot: their
   *  derivations re-derive until the next document. */
  mutatedTodos: Set<string>;
  /** Armed rows' source class per project, as served. */
  sourceClass: Map<string, ArmedRow["source"]["source_class"]>;
  dispositions: Map<string, InboxMessage["disposition"]>;
  settingsState: AppSettings;
  annotationList: AnnotationThread[];
  threadList: MessageThread[];
  entryFileCache: Map<string, string>;
  /** Entry files' served sha256, keyed like the content
   *  cache — the guarded save's compare-and-swap base,
   *  served by the file route, never computed locally. */
  entryFileShas: Map<string, string>;
  /** Each plan's write coordinates for the resolve route:
   *  its plans-dir path and the file sha256 the document
   *  served for it, keyed by bundle. */
  planWrite: Map<string, { path: string; sha256: string }>;
  lastRefresh: Date;
  care: ServerCare;
}

export interface LiveHost {
  doc: WorkbenchFeeds;
  s: LiveState;
  channel: WbChannel | null;
  clock: () => Date;
  emit(): void;
  url(path: string): string;
  postJson<T>(path: string, body: unknown): Promise<T>;
  entryAction<T = Record<string, unknown>>(
    e: Entry,
    body: Record<string, unknown>,
  ): Promise<T>;
  entry(id: string): Entry | undefined;
  plan(bundle: string): Plan | undefined;
  todo(id: string): FileTodo | undefined;
  repo(slug: string): Repo | undefined;
  board(): BoardCard[];
  serverCare(): ServerCare;
  freshnessLabel(): string;
  setEntryReview(
    id: string,
    review: "approved" | "needs-changes" | "stale",
    note?: string,
  ): Promise<Entry>;
}
