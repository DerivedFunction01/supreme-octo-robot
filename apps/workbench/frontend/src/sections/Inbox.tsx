import { useAdapter, useStoreVersion } from "../lib/store";
import { useNav } from "../lib/nav";
import type { InboxMessage } from "../lib/types";
import {
  Group,
  GroupLabel,
  Lab,
  LargeTitle,
  Row,
  Subtitle,
} from "../components/ui";

// Frame 7 · Inbox — the message store's surface: items
// awaiting a first disposition carry Open / Dismiss; Open
// navigates to the item's own surface and records the
// disposition, Dismiss records it in place. Dispositioned
// items collect below with their outcome on their face.

const KIND_CHIP: Record<InboxMessage["kind"], { label: string; warn?: boolean }> = {
  mockup: { label: "Mockup" },
  doctor: { label: "Doctor", warn: true },
  plan: { label: "Plan" },
};

function KindChip({ kind }: { kind: InboxMessage["kind"] }) {
  const k = KIND_CHIP[kind];
  return (
    <span
      className="inline-flex flex-[0_0_auto] items-center gap-1.5 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
      style={{
        backgroundColor: k.warn
          ? "color-mix(in srgb, var(--ui-okabe-orange) 16%, transparent)"
          : "color-mix(in srgb, var(--ui-okabe-blue) 12%, transparent)",
        color: k.warn ? "var(--ui-status-stale-text)" : "var(--ui-status-canonical-text)",
      }}
    >
      {k.label}
    </span>
  );
}

function OutcomeChip({ disposition }: { disposition: NonNullable<InboxMessage["disposition"]> }) {
  const label = disposition === "filed" ? "Filed" : disposition === "opened" ? "Opened" : "Dismissed";
  return (
    <span
      className="ml-auto inline-flex flex-none rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
      style={{
        backgroundColor:
          disposition === "dismissed"
            ? "var(--ui-surface-sunken)"
            : "color-mix(in srgb, var(--ui-okabe-bluish-green) 14%, transparent)",
        color:
          disposition === "dismissed"
            ? "var(--ui-content-secondary)"
            : "var(--ui-status-implemented-text)",
      }}
    >
      {label}
    </span>
  );
}

export function Inbox() {
  useStoreVersion();
  const a = useAdapter();
  const { navigate, setProject } = useNav();
  const messages = a.messages();
  const awaiting = messages.filter((m) => m.disposition === null);
  const dispositioned = messages.filter((m) => m.disposition !== null);

  const open = (m: InboxMessage) => {
    const updated = a.openMessage(m.id);
    const t = updated.target;
    if (t.section === "mockups") {
      setProject(t.project ?? m.project);
      navigate({ section: "mockup", entryId: t.entryId });
    } else if (t.section === "plans") {
      navigate({ section: "plans", bundle: t.bundle });
    } else {
      navigate({ section: "overview" });
    }
  };

  return (
    <div className="px-[26px] py-[22px]">
      <LargeTitle>Inbox</LargeTitle>
      <Subtitle>
        {awaiting.length} awaiting a first disposition
      </Subtitle>
      <Group>
        {awaiting.map((m, i) => (
          <Row key={m.id} last={i === awaiting.length - 1}>
            {/* Two-line discipline (the kit Row form, owner's
                row ruling): line 1 is the kind chip +
                the truncating title; the actions ride line 2
                beside the truncating sub, flex-none — neither
                text line competes with the chips for width, so
                the row can never balloon at phone width. */}
            <div className="min-w-0 flex-1">
              <div className="flex flex-nowrap items-center gap-3">
                <KindChip kind={m.kind} />
                <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{m.title}</span>
              </div>
              <div className="flex flex-nowrap items-center gap-2">
                <span
                  className="min-w-0 flex-1 truncate text-[12.5px]"
                  style={{ color: "var(--ui-content-secondary)" }}
                >
                  {m.project} · {m.arrivedLabel}
                </span>
                <span className="ml-auto flex flex-none gap-2">
                  <button
                    type="button"
                    onClick={() => open(m)}
                    className="rounded-full px-2.5 py-[6px] text-xs font-semibold"
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--ui-okabe-blue) 12%, transparent)",
                      color: "var(--ui-status-canonical-text)",
                    }}
                  >
                    Open
                  </button>
                  <button
                    type="button"
                    onClick={() => void a.dismissMessage(m.id)}
                    className="rounded-full px-2.5 py-[6px] text-xs font-semibold"
                    style={{
                      backgroundColor: "var(--ui-surface-sunken)",
                      color: "var(--ui-content-secondary)",
                    }}
                  >
                    Dismiss
                  </button>
                </span>
              </div>
            </div>
          </Row>
        ))}
        {awaiting.length === 0 ? (
          <Row last>
            <Lab>Nothing awaiting a disposition</Lab>
          </Row>
        ) : null}
      </Group>

      <GroupLabel>Dispositioned</GroupLabel>
      <Group>
        {dispositioned.map((m, i) => (
          <Row key={m.id} last={i === dispositioned.length - 1}>
            <div className="min-w-0 flex-1">
              <div className="flex flex-nowrap items-center gap-3">
                <KindChip kind={m.kind} />
                <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{m.title}</span>
              </div>
              <div className="flex flex-nowrap items-center gap-2">
                <span
                  className="min-w-0 flex-1 truncate text-[12.5px]"
                  style={{ color: "var(--ui-content-secondary)" }}
                >
                  {m.project} · {m.arrivedLabel}
                </span>
                <OutcomeChip disposition={m.disposition!} />
              </div>
            </div>
          </Row>
        ))}
        {dispositioned.length === 0 ? (
          <Row last>
            <Lab>Nothing dispositioned yet</Lab>
          </Row>
        ) : null}
      </Group>
    </div>
  );
}
