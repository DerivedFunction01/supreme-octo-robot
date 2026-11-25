import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import {
  Chev,
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

// Frame 1 · Home — the cross-project rollup (lib/derived/home.py's
// served shape): project rows with health dot, summary line,
// and the project's standing chip; across-projects facts below.

const DOT: Record<string, string> = {
  ok: "var(--ui-okabe-bluish-green)",
  warn: "var(--ui-okabe-orange)",
  muted: "var(--ui-content-muted)",
};

export function Home() {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, setProject } = useNav();
  const summary = a.homeSummary();
  const rollups = a.projectRollups();

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Home</LargeTitle>
      <Subtitle>
        {summary.sweptCount} projects swept · server {summary.serverHealthy ? "healthy" : "down"} ·
        editing {summary.editingOn ? "on" : "off"} · updated {a.freshnessLabel()}
      </Subtitle>

      <GroupLabel>Projects</GroupLabel>
      <Group>
        {rollups.map((r, i) => (
          <Row
            key={r.project.slug}
            last={i === rollups.length - 1}
            onClick={() => {
              setProject(r.project.slug);
              navigate({ section: "overview" });
            }}
          >
            <span
              className="ml-1 block h-2.5 w-2.5 flex-[0_0_10px] rounded-full"
              style={{ backgroundColor: DOT[r.dot] }}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14.5px] font-medium">{r.project.name}</span>
              <Sub truncate>{r.sub}</Sub>
            </span>
            <span className="ml-auto shrink-0">
              {r.chip.type === "ruled" ? (
                <RuledChip status={r.chip.status} />
              ) : r.chip.type === "badge" ? (
                <ReviewBadge kind={r.chip.kind} text={r.chip.text} />
              ) : (
                <span
                  className="inline-flex max-w-full rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
                  style={{ backgroundColor: "var(--ui-surface-sunken)", color: "var(--ui-content-secondary)" }}
                >
                  <span className="truncate">{r.chip.text}</span>
                </span>
              )}
            </span>
            <Chev />
          </Row>
        ))}
      </Group>

      <GroupLabel>Across projects</GroupLabel>
      <Group>
        <Row>
          <Lab>Awaiting review</Lab>
          <Val>
            {summary.awaitingReview} item{summary.awaitingReview === 1 ? "" : "s"}
          </Val>
        </Row>
        <Row last>
          <Lab>Doing now</Lab>
          <Val>
            {summary.doingNow} todo{summary.doingNow === 1 ? "" : "s"}
          </Val>
        </Row>
      </Group>
    </div>
  );
}
