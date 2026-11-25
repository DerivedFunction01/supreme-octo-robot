import { useState } from "react";
import { Lane } from "@kit/components/display/Lane";
import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { BoardCard } from "../lib/seam";
import { LargeTitle, ReviewBadge, RuledChip, Subtitle } from "../components/ui";

// Frame 6 · Board — the unified collection in four lanes.
// Cards are live store items: dragging a todo card writes its
// status through the one mutation path (arming side effects
// included), a plan card moves the plan's state, and a review
// card dropped on Done records the approve verdict. Clicking
// a card opens its own surface.

const LANES: { key: BoardCard["lane"]; title: string; accent?: boolean }[] = [
  { key: "review", title: "Review queue", accent: true },
  { key: "todo", title: "To do" },
  { key: "doing", title: "Doing" },
  { key: "done", title: "Done" },
];

function CardView({
  card,
  onOpen,
}: {
  card: BoardCard;
  onOpen: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/ui-card", card.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={onOpen}
      className="cursor-pointer p-[11px_12px]"
      style={{
        backgroundColor: "var(--ui-surface-2)",
        border: "1px solid var(--ui-border-default)",
        borderRadius: "var(--ui-radius-md)",
      }}
      role="button"
      aria-label={card.title}
    >
      <div
        className="truncate text-[11px] font-bold tracking-[0.03em]"
        style={{ color: "var(--ui-status-canonical-text)" }}
      >
        {card.projectTag}
      </div>
      <div className="my-[3px] text-[13.5px] leading-[1.3] font-semibold [overflow-wrap:anywhere]">{card.title}</div>
      <div
        className="flex flex-wrap items-center gap-2 text-xs"
        style={{ color: "var(--ui-content-secondary)" }}
      >
        {card.meta ? <span className="min-w-0 truncate">{card.meta}</span> : null}
        {card.badge?.kind === "review" ? (
          <ReviewBadge
            kind={card.badge.text as "in-triage" | "needs-changes"}
            text={
              card.badge.text === "in-triage"
                ? "In triage"
                : `Needs changes · ${card.badge.count ?? 1} open`
            }
          />
        ) : null}
        {card.badge?.kind === "gate" ? <RuledChip status="hard-gate" /> : null}
        {card.ruled ? <RuledChip status={card.ruled} /> : null}
      </div>
    </div>
  );
}

const DONE_PAGE = 8;

export function Board() {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, setProject } = useNav();
  const settings = a.settings();
  const cards = a.board();
  const [overLane, setOverLane] = useState<string | null>(null);
  // Done-lane pagination (W15): the lane pages over the
  // seam's boardDone window instead of rendering the whole
  // history at once.
  const [doneShown, setDoneShown] = useState(DONE_PAGE);
  const doneWindow = a.boardDone(0, doneShown);

  const open = (card: BoardCard) => {
    if (card.target.kind === "entry") {
      const e = a.entry(card.target.id);
      if (e) setProject(e.project);
      navigate({ section: "mockup", entryId: card.target.id });
    } else if (card.target.kind === "plan") {
      const p = a.plan(card.target.bundle);
      if (p) setProject(p.project);
      navigate({ section: "plans", bundle: card.target.bundle });
    } else {
      const t = a.todo(card.target.id);
      if (t) setProject(t.project);
      navigate({ section: "todos" });
    }
  };

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Board</LargeTitle>
      <Subtitle>All projects · updated {a.freshnessLabel()} · drag a card to move it</Subtitle>
      <div className="flex gap-3.5 overflow-x-auto pb-1">
        {LANES.map((lane) => {
          const laneCards =
            lane.key === "done" ? doneWindow.cards : cards.filter((c) => c.lane === lane.key);
          const laneCount = lane.key === "done" ? doneWindow.total : laneCards.length;
          const doingCount = lane.key === "doing" ? laneCards.length : 0;
          return (
            <div
              key={lane.key}
              className="min-w-0 flex-1"
              style={{ minWidth: Math.min(settings.boardLaneWidth, 300) }}
              onDragOver={(e) => {
                e.preventDefault();
                setOverLane(lane.key);
              }}
              onDragLeave={() => setOverLane(null)}
              onDrop={(e) => {
                e.preventDefault();
                const id = e.dataTransfer.getData("text/ui-card");
                if (id) void a.moveBoardCard(id, lane.key);
                setOverLane(null);
              }}
            >
              <Lane
                title={lane.title}
                count={laneCount}
                accent={lane.accent}
                countWarning={doingCount > 7}
              >
                <div
                  className="flex min-h-[120px] flex-col gap-2"
                  style={{
                    outline: overLane === lane.key ? "2px dashed var(--ui-accent)" : undefined,
                    outlineOffset: 2,
                    borderRadius: "var(--ui-radius-md)",
                  }}
                >
                  {laneCards.map((c) => (
                    <CardView key={c.id} card={c} onOpen={() => open(c)} />
                  ))}
                  {laneCards.length === 0 ? (
                    <p className="p-2 text-xs" style={{ color: "var(--ui-content-muted)" }}>
                      Drop cards here
                    </p>
                  ) : null}
                  {lane.key === "done" && doneShown < doneWindow.total ? (
                    <button
                      type="button"
                      onClick={() => setDoneShown((n) => n + DONE_PAGE)}
                      className="p-2 text-left text-xs font-semibold"
                      style={{ color: "var(--ui-accent)" }}
                    >
                      Show more · {doneWindow.total - doneShown} older done cards
                    </button>
                  ) : null}
                </div>
              </Lane>
            </div>
          );
        })}
      </div>
    </div>
  );
}
