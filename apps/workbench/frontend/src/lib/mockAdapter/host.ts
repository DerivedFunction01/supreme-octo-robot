// The mock adapter's shared context: the seeded store
// plus the services the adapter class itself owns. The
// feature modules under mockAdapter/ are plain
// functions over this context; the class in
// mockAdapter.ts builds it and delegates.

import type { BoardCard } from "../seam";
import type { SeedDb } from "../seed";
import type {
  AppSettings,
  Entry,
  FileTodo,
  Plan,
  Repo,
  ServerCare,
} from "../types";

export interface MockState {
  db: SeedDb;
  settingsState: AppSettings;
  /** Saved entry-file bodies, keyed `id|path` — a save
   *  replaces the stand-in body entryFileBody serves. */
  entryFileOverrides: Map<string, string>;
  care: ServerCare;
  lastRefresh: Date;
}

export interface MockHost {
  s: MockState;
  clock: () => Date;
  emit(): void;
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
