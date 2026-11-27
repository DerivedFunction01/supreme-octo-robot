import { useEffect, useState } from "react";
import { useAdapter } from "../lib/store";
import type {
  TaskManagerProcess,
  TaskManagerResult,
} from "../lib/liveAdapter/taskManager";
import {
  ActionRow,
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Sub,
  Subtitle,
  Val,
} from "../components/ui";

// Task Manager — the load monitor's snapshot, served ready
// by GET /api/task-manager through the seam. The section
// renders the served shape only: a stat-and-range header,
// the live venues, and the process ledger heaviest first.
// Long argv clamps on the row and expands in place. The one
// act is routing a finding to a process's owning thread —
// a sent message thread carrying the finding, through the
// seam's compose verb. No kill act: that scope is unruled.

const POLL_MS = 15_000;

function fmtGb(kb: number): string {
  return `${(kb / 1_048_576).toFixed(1)} GB`;
}

function fmtElapsed(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function processName(p: TaskManagerProcess): string {
  const head = p.argv[0]?.split("/").pop() ?? "?";
  const script = p.argv[1] && !p.argv[1].startsWith("-")
    ? ` ${p.argv[1].split("/").pop()}`
    : "";
  return `${head}${script}`;
}

export function TaskManager() {
  const a = useAdapter();
  const [result, setResult] = useState<TaskManagerResult | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [routed, setRouted] = useState<ReadonlySet<number>>(new Set());

  useEffect(() => {
    let live = true;
    const pull = () => {
      void a.taskManager().then((r) => {
        if (live) setResult(r);
      });
    };
    pull();
    const id = window.setInterval(pull, POLL_MS);
    return () => {
      live = false;
      window.clearInterval(id);
    };
  }, [a]);

  if (result === null) {
    return (
      <div className="px-[26px] py-[22px]">
        <LargeTitle>Task Manager</LargeTitle>
        <Subtitle>Loading</Subtitle>
      </div>
    );
  }
  if (!result.ok) {
    return (
      <div className="px-[26px] py-[22px]">
        <LargeTitle>Task Manager</LargeTitle>
        <Subtitle>{result.reason}</Subtitle>
      </div>
    );
  }
  const snap = result.snapshot;
  const routeFinding = (p: TaskManagerProcess) => {
    const body = [
      `Load finding (Task Manager): ${processName(p)} pid ${p.pid} at ${p.cpu_pct.toFixed(1)}% CPU, ${p.mem_pct.toFixed(1)}% memory, running ${fmtElapsed(p.elapsed_s)}.`,
      `argv: ${p.argv.join(" ")}`,
      `cwd: ${p.cwd}`,
      snap.load
        ? `Machine load at the snapshot: ${snap.load[0]} / ${snap.load[1]} / ${snap.load[2]} on ${snap.cpus} CPUs.`
        : "Machine load at the snapshot: unavailable.",
      `Live venues: ${snap.venues.filter((v) => v.live).map((v) => `${v.kind}:${v.name}`).join(", ") || "none"}.`,
      "Venue rule: no checks or code run locally while the fleet is up — re-route this work to a live venue.",
    ].join("\n");
    void a
      .composeThread({ project: p.repo ?? "", body, sendNow: true })
      .then(() => setRouted((prev) => new Set(prev).add(p.pid)));
  };

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Task Manager</LargeTitle>
      <Subtitle>
        {snap.stale
          ? `Snapshot stale${snap.stamp ? ` · ${snap.stamp}` : ""}`
          : `Snapshot ${snap.stamp ?? ""}`}
      </Subtitle>

      {snap.load && snap.cpus !== null && snap.mem ? (
        <>
          <GroupLabel>Machine</GroupLabel>
          <Group>
            <Row>
              <Lab>Load 1m</Lab>
              <Val mono>{snap.load[0].toFixed(2)}</Val>
            </Row>
            <Row>
              <Lab>Load 5m</Lab>
              <Val mono>{snap.load[1].toFixed(2)}</Val>
            </Row>
            <Row>
              <Lab>Load 15m</Lab>
              <Val mono>{snap.load[2].toFixed(2)}</Val>
            </Row>
            <Row>
              <Lab>CPUs</Lab>
              <Val mono>{snap.cpus}</Val>
            </Row>
            <Row last>
              <Lab>Memory used</Lab>
              <Val>
                {fmtGb(snap.mem.used_kb)} of {fmtGb(snap.mem.total_kb)} (
                {((snap.mem.used_kb / snap.mem.total_kb) * 100).toFixed(0)}%)
              </Val>
            </Row>
          </Group>
        </>
      ) : null}

      <GroupLabel>Venues</GroupLabel>
      <Group>
        {snap.venues.length === 0 ? (
          <Row last>
            <Lab>No live venue</Lab>
          </Row>
        ) : (
          snap.venues.map((v, i) => (
            <Row key={`${v.kind}:${v.name}`} last={i === snap.venues.length - 1}>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14.5px] font-medium">{v.name}</span>
                <Sub truncate>{v.kind}</Sub>
              </span>
              <Val>
                {v.live
                  ? v.in_flight !== null
                    ? `${v.in_flight} in flight`
                    : "live"
                  : "down"}
              </Val>
            </Row>
          ))
        )}
      </Group>

      <GroupLabel>Processes</GroupLabel>
      <Group>
        {snap.processes.length === 0 ? (
          <Row last>
            <Lab>{snap.stale ? "No current snapshot" : "No processes"}</Lab>
          </Row>
        ) : (
          snap.processes.map((p, i) => (
            <div key={p.pid}>
              <Row
                onClick={() => setExpanded(expanded === p.pid ? null : p.pid)}
                last={i === snap.processes.length - 1 && expanded !== p.pid}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium">
                    {processName(p)}
                  </span>
                  <Sub truncate>{p.repo ?? p.cwd}</Sub>
                </span>
                <Val mono>
                  {p.cpu_pct.toFixed(1)}% · {p.mem_pct.toFixed(1)}%
                </Val>
              </Row>
              {expanded === p.pid ? (
                <div className="px-[14px] py-[10px]">
                  <Sub>{p.argv.join(" ")}</Sub>
                  <Sub>
                    pid {p.pid} · ppid {p.ppid} · elapsed {fmtElapsed(p.elapsed_s)}
                  </Sub>
                  <Sub>{p.cwd}</Sub>
                  {p.thread ? <Sub>{p.thread}</Sub> : null}
                  {p.thread ? (
                    routed.has(p.pid) ? (
                      <Sub>Finding routed</Sub>
                    ) : (
                      <ActionRow
                        label="Route finding to owning thread"
                        onClick={() => routeFinding(p)}
                        last
                      />
                    )
                  ) : null}
                </div>
              ) : null}
            </div>
          ))
        )}
      </Group>
    </div>
  );
}
