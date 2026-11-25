import { useState } from "react";
import { ArmConfirm } from "@kit/components/shell/ArmConfirm";
import { Button } from "@kit/components/controls/Button";
import { Sheet } from "@kit/components/shell/Sheet";
import { Toggle } from "@kit/components/controls/Toggle";
import { useAdapter, useStoreVersion } from "../lib/store";
import {
  ActionRow,
  Chev,
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Sub,
  Subtitle,
  TOGGLE_LABEL_SR_ONLY,
  Val,
} from "../components/ui";

// Frame 9 · Settings — Workbench. This section carries only
// workbench-specific settings: the lane width drives the
// Board, and the guarded-saves switch is the config gate the
// editor's Save answers to. The shared appearance axes
// (palette × mode × density) are NOT restated here — they
// live in the superapp shell's unified Settings and arrive
// as the shell-provided root attributes (consolidation
// ruling).

const LANE_WIDTHS = [240, 264, 288, 320];

export function Settings() {
  useStoreVersion();
  const a = useAdapter();
  const s = a.settings();
  const [widthOpen, setWidthOpen] = useState(false);
  const [housekeeping, setHousekeeping] = useState("");
  const workspace = a.workspaceConfig();
  const counts = a.messageCounts();
  const care = a.serverCare();

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Workbench</LargeTitle>
      <Subtitle>Settings · this app</Subtitle>

      <GroupLabel>Display</GroupLabel>
      <Group>
        <Row last onClick={() => setWidthOpen(true)}>
          <Lab>Board lane width</Lab>
          <Val>{s.boardLaneWidth} px</Val>
          <Chev />
        </Row>
      </Group>

      <GroupLabel>Editing</GroupLabel>
      <Group>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Guarded file saves</span>
            <Sub>Sha-checked, config-gated saves from the viewer</Sub>
          </span>
          <span className="ml-auto">
            <Toggle
              checked={s.guardedSaves}
              onChange={(v) => a.updateSettings({ guardedSaves: v })}
              label="Guarded file saves"
              className={TOGGLE_LABEL_SR_ONLY}
            />
          </span>
        </Row>
        <Row last>
          <Lab>Server</Lab>
          <Val>{s.serverLabel}</Val>
        </Row>
      </Group>

      <GroupLabel>Sweep</GroupLabel>
      <Group>
        <Row>
          <Lab>Projects swept</Lab>
          <Val>{s.projectsSwept}</Val>
        </Row>
        <Row last>
          <Lab>Doctor</Lab>
          <Val>{s.doctorLabel}</Val>
        </Row>
      </Group>

      <GroupLabel>Workspace</GroupLabel>
      <Group>
        {workspace.map((row, i) => (
          <Row key={row.label} last={i === workspace.length - 1}>
            <Lab>{row.label}</Lab>
            <Val>{row.value}</Val>
          </Row>
        ))}
      </Group>

      <GroupLabel>Messages</GroupLabel>
      <Group>
        {counts.map((row) => (
          <Row key={row.label}>
            <Lab>{row.label}</Lab>
            <Val>{row.count}</Val>
          </Row>
        ))}
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Clean up dismissed</span>
            <Sub>Remove messages already dispositioned as dismissed</Sub>
          </span>
          <span className="ml-auto">
            <ArmConfirm
              label="Clean up"
              confirmLabel="Confirm cleanup"
              statement="Remove every dismissed message from the store. Filed and opened messages stay."
              disarmKey={`cleanup|${counts.map((c) => c.count).join(",")}`}
              onConfirm={() => {
                const { removed } = a.cleanupMessages();
                setHousekeeping(`Cleaned up ${removed} dismissed message${removed === 1 ? "" : "s"}.`);
              }}
            />
          </span>
        </Row>
        <Row last>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Purge dispositioned</span>
            <Sub>Remove every message that carries a disposition</Sub>
          </span>
          <span className="ml-auto">
            <ArmConfirm
              label="Purge"
              confirmLabel="Confirm purge"
              statement="Remove every dispositioned message — filed, opened and dismissed. Messages awaiting disposition stay."
              variant="danger"
              disarmKey={`purge|${counts.map((c) => c.count).join(",")}`}
              onConfirm={() => {
                const { removed } = a.purgeMessages();
                setHousekeeping(`Purged ${removed} dispositioned message${removed === 1 ? "" : "s"}.`);
              }}
            />
          </span>
        </Row>
      </Group>
      {housekeeping ? (
        <p className="mt-2 text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
          {housekeeping}
        </p>
      ) : null}

      <GroupLabel>Server care</GroupLabel>
      <Group>
        <Row>
          <Lab>Link</Lab>
          <Val>{care.linkState === "ok" ? "Connected" : "Down"}</Val>
        </Row>
        <Row>
          <Lab>Classification</Lab>
          <Val>{care.classification}</Val>
        </Row>
        <Row>
          <Lab>Stray processes</Lab>
          <Val>{care.strayCount}</Val>
        </Row>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Clear strays</span>
            <Sub>The ladder's first rung — stray server processes are cleared before any restart</Sub>
          </span>
          <span className="ml-auto">
            <ArmConfirm
              label="Clear strays"
              confirmLabel="Confirm clear"
              statement="Clear the stray server processes. The supervised server itself is not touched."
              disabled={care.strayCount === 0}
              disabledReason={care.strayCount === 0 ? "No strays to clear." : undefined}
              disarmKey={`strays|${care.strayCount}`}
              onConfirm={() => a.repairAction("clear-strays")}
            />
          </span>
        </Row>
        <Row>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14.5px] font-medium">Fallback start</span>
            <Sub>Start the server directly when the supervised unit is down</Sub>
          </span>
          <span className="ml-auto">
            <ArmConfirm
              label="Fallback start"
              confirmLabel="Confirm start"
              statement="Run the fallback start. Use it only when the link is down and the supervised unit has not recovered."
              disarmKey={`fallback|${care.lastRepairLabel}`}
              onConfirm={() => a.repairAction("fallback-restart")}
            />
          </span>
        </Row>
        <Row last={care.log.length === 0}>
          <Lab>Last repair</Lab>
          <Val>{care.lastRepairLabel}</Val>
        </Row>
        {care.log.map((line, i) => (
          <Row key={i} last={i === care.log.length - 1}>
            <Sub>{line}</Sub>
          </Row>
        ))}
        {care.log.length === 0 ? (
          <Row last>
            <Lab>No repair events recorded</Lab>
          </Row>
        ) : null}
      </Group>

      <GroupLabel>Refresh</GroupLabel>
      <Group>
        <Row>
          <Lab>Last refresh</Lab>
          <Val>{a.freshnessLabel()}</Val>
        </Row>
        <ActionRow label="Refresh now" onClick={() => void a.refresh()} />
        <ActionRow label="Rescan projects" last onClick={() => void a.rescan()} />
      </Group>

      <Sheet
        open={widthOpen}
        title="Board lane width"
        onClose={() => setWidthOpen(false)}
        footer={
          <Button variant="secondary" onClick={() => setWidthOpen(false)}>
            Done
          </Button>
        }
      >
        <Group>
          {LANE_WIDTHS.map((w, i) => (
            <Row
              key={w}
              last={i === LANE_WIDTHS.length - 1}
              onClick={() => {
                a.updateSettings({ boardLaneWidth: w });
                setWidthOpen(false);
              }}
            >
              <Lab>{w} px</Lab>
              {s.boardLaneWidth === w ? (
                <span className="ml-auto font-bold" style={{ color: "var(--ui-accent)" }}>
                  ✓
                </span>
              ) : null}
            </Row>
          ))}
        </Group>
        <p className="mt-3 text-[13px]" style={{ color: "var(--ui-content-secondary)" }}>
          Applies to the Board's lanes immediately.
        </p>
      </Sheet>
    </div>
  );
}
