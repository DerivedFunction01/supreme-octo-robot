import { useState } from "react";
import { Chip } from "@kit/components/controls/Chip";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { EntryKind, RuledStatus } from "../lib/types";
import { PickChip } from "./Mockups";
import {
  Chev,
  Group,
  LargeTitle,
  ReviewBadge,
  Row,
  RuledChip,
  Subtitle,
} from "../components/ui";

// Frame 11 · Entries — the unified collection (SPEC §8.5):
// two filter rows (kind, then ruled status) over the
// project's registry entries. A row opens the entry's own
// surface: mockups drill in, docs peek, plans open Plans.

const KINDS: { value: EntryKind | "all"; label: string }[] = [
  { value: "all", label: "All kinds" },
  { value: "mockup", label: "Mockups" },
  { value: "plan", label: "Plans" },
  { value: "doc", label: "Docs" },
];

const STATUSES: { value: RuledStatus | "any"; label: string }[] = [
  { value: "any", label: "Any status" },
  { value: "unexplored", label: "Unexplored" },
  { value: "implemented", label: "Implemented" },
  { value: "canonical", label: "Canonical" },
];

const KIND_PILL: Record<EntryKind, { label: string; blue: boolean; purple: boolean }> = {
  mockup: { label: "Mockup", blue: true, purple: false },
  plan: { label: "Plan", blue: false, purple: false },
  doc: { label: "Doc", blue: false, purple: false },
};

export function Entries() {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, project, setProject } = useNav();
  const [kind, setKind] = useState<EntryKind | "all">("all");
  const [status, setStatus] = useState<RuledStatus | "any">("any");
  const all = a.entries(project);
  const unexplored = all.filter((e) => e.status === "unexplored").length;
  const shown = all.filter(
    (e) => (kind === "all" || e.kind === kind) && (status === "any" || e.status === status),
  );

  const open = (id: string) => {
    const e = a.entry(id);
    if (!e) return;
    if (e.kind === "mockup") {
      setProject(e.project);
      navigate({ section: "mockup", entryId: e.id });
    } else if (e.repoPath) {
      navigate({ section: "peek", repo: e.repoPath.repo, path: e.repoPath.path, tab: "content" });
    } else {
      navigate({ section: "plans" });
    }
  };

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Entries</LargeTitle>
      <Subtitle>
        {all.length} registered · {unexplored} unexplored
      </Subtitle>
      <div className="mb-2 flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <PickChip key={k.value} label={k.label} on={kind === k.value} onPress={() => setKind(k.value)} />
        ))}
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {STATUSES.map((s) =>
          s.value === "any" ? (
            <PickChip key="any" label="Any status" on={status === "any"} onPress={() => setStatus("any")} />
          ) : (
            <Chip
              key={s.value}
              status={s.value}
              pressed={status === s.value}
              onPress={() => setStatus(status === s.value ? "any" : s.value)}
            />
          ),
        )}
      </div>
      <Group>
        {shown.map((e, i) => {
          const pill = KIND_PILL[e.kind];
          return (
            <Row key={e.id} last={i === shown.length - 1} onClick={() => open(e.id)}>
              {/* Two-line discipline (the kit Row form, owner's
                  row ruling 2026-11-13): line 1 is the kind pill +
                  the truncating title + chevron; the review badge
                  rides line 2 beside the truncating sub, flex-none
                  — neither text line competes with the badge for
                  width, so the row can never balloon at phone
                  width. */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-nowrap items-center gap-3">
                  <span
                    className="inline-flex flex-none rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                    style={{
                      backgroundColor: pill.blue
                        ? "color-mix(in srgb, var(--wb-okabe-blue) 12%, transparent)"
                        : e.kind === "mockup"
                          ? "color-mix(in srgb, var(--wb-okabe-reddish-purple) 14%, transparent)"
                          : "var(--wb-surface-sunken)",
                      color: pill.blue
                        ? "var(--wb-status-canonical-text)"
                        : e.kind === "mockup"
                          ? "var(--wb-status-unexplored-text)"
                          : "var(--wb-content-secondary)",
                    }}
                  >
                    {pill.label}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{e.title}</span>
                  <Chev />
                </div>
                <div className="flex flex-nowrap items-center gap-2">
                  <span
                    className="min-w-0 flex-1 truncate text-[12.5px]"
                    style={{ color: "var(--wb-content-secondary)" }}
                  >
                    {e.registeredLabel} · v{e.version}
                  </span>
                  <span className="ml-auto flex flex-none items-center">
                    {e.review === "in-triage" ? (
                      <ReviewBadge kind="in-triage" text="In triage" />
                    ) : e.review === "needs-changes" ? (
                      <ReviewBadge kind="needs-changes" text={`Needs changes · ${e.reviewCount ?? 1}`} />
                    ) : e.review === "approved" ? (
                      <ReviewBadge kind="approved" text="Approved" stateHash={e.stateHash} />
                    ) : e.staleNote ? (
                      <ReviewBadge kind="stale" text={e.staleNote} />
                    ) : (
                      <RuledChip status={e.status} />
                    )}
                  </span>
                </div>
              </div>
            </Row>
          );
        })}
        {shown.length === 0 ? (
          <Row last>
            <span className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              No entries match these filters.
            </span>
          </Row>
        ) : null}
      </Group>
    </div>
  );
}
