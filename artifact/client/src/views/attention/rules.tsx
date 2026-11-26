// Rules — the original's renderRules(): the tables
// grouped by presence scope under the hard-stop floor
// banner; a row opens the full rule editor (the sheet
// in rule-drawer.tsx, the original's openDrawer()).

import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import {
  DataTable,
  type DataTableColumn,
} from "@workhorse/kit/components/display/DataTable";
import { EmptyState } from "@workhorse/kit/components/display/EmptyState";
import {
  GroupedList,
  NoticeRow,
  Row,
  StatRow,
} from "@workhorse/kit/components/display/GroupedList";
import { StatusChip } from "@workhorse/kit/components/display/StatusChip";
import {
  type AttentionRule,
  type RegistriesPayload,
  type RulesPayload,
} from "./model";
import { RuleDrawer, SCOPES } from "./rule-drawer";
import { api, call, usePortion } from "./transport";
import { BandHead, PageColumn, ScopeLine, useAttentionUi } from "./ui";

/** The hard-stop floor's classes — each its own row
 *  in the group under the banner, never a joined
 *  string carried inside the notice itself. */
const HARD_STOP_CLASSES = [
  "Permission cards",
  "Scope expansions",
  "Logins",
  "External sends",
  "Purchases",
  "Form submits",
  "Calendar writes",
  "Schedule changes",
];

const RULE_COLUMNS: DataTableColumn<AttentionRule>[] = [
  {
    key: "id",
    header: "Rule",
    render: (r) => <b>{r.display_name || r.id}</b>,
  },
  { key: "when_label", header: "When" },
  { key: "then_label", header: "Then" },
  {
    key: "mode",
    header: "Mode",
    render: (r) => (
      <StatusChip tone={r.mode === "shadow" ? "warn" : "ok"} label={r.mode || "active"} />
    ),
  },
];

/** One scope's rules in two forms: the table above
 *  the phone breakpoint; below it, each rule a grouped
 *  list — its name the group title (a button, opening
 *  the editor as a table row does), When / Then / Mode
 *  as labelled rows carrying their full values, the
 *  mode chip whole. The swap is the scoped media block
 *  in the client stylesheet (att-rules-reform). */
function RuleTable({
  label,
  rules,
  onOpen,
}: {
  label: string;
  rules: AttentionRule[];
  onOpen: (rule: AttentionRule | null) => void;
}) {
  return (
    <div className="att-rules-reform">
      <DataTable<AttentionRule>
        ariaLabel={`${label} rules`}
        className="att-reform-table"
        columns={RULE_COLUMNS}
        rows={rules}
        rowKey={(r) => r.id}
        onRowSelect={(key) => onOpen(rules.find((r) => r.id === key) ?? null)}
      />
      <div className="att-reform-cards" aria-label={`${label} rules`}>
        {rules.map((r) => (
          <GroupedList key={r.id} className="mb-3">
            <button
              type="button"
              onClick={() => onOpen(r)}
              className="flex min-h-[47px] w-full cursor-pointer items-center border-0 bg-transparent px-3.5 py-[11px] text-left hover:bg-(--ui-surface-1) focus-visible:outline-2 focus-visible:outline-(--ui-focus-ring)"
            >
              <span
                className="min-w-0 flex-1 text-[14.5px] font-semibold [overflow-wrap:anywhere]"
                style={{ color: "var(--ui-content-primary)" }}
              >
                {r.display_name || r.id}
              </span>
            </button>
            <StatRow label="When">{r.when_label}</StatRow>
            <StatRow label="Then">{r.then_label}</StatRow>
            <StatRow label="Mode">
              <StatusChip
                tone={r.mode === "shadow" ? "warn" : "ok"}
                label={r.mode || "active"}
              />
            </StatRow>
          </GroupedList>
        ))}
      </div>
    </div>
  );
}

export function RulesView() {
  const ui = useAttentionUi();
  const rulesP = usePortion<RulesPayload>("rules", () => call(api.getRules({})), ui.refreshKey);
  const regP = usePortion<RegistriesPayload>(
    "registries",
    () => call(api.getRegistries({})),
    ui.refreshKey,
  );
  const [drawer, setDrawer] = useState<{ rule: AttentionRule | null } | null>(null);

  if (!rulesP.data) {
    return (
      <PageColumn>
        {rulesP.loading ? (
          <ScopeLine>Loading…</ScopeLine>
        ) : (
          <EmptyState message="Rules could not be loaded." />
        )}
      </PageColumn>
    );
  }

  const rules = [...rulesP.data.rules].sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100));
  const active = rules.filter((r) => r.mode !== "shadow").length;

  const openDrawer = (rule: AttentionRule | null) => {
    if (!regP.data) {
      ui.notify("Registries still loading.");
      return;
    }
    setDrawer({ rule });
  };

  return (
    <PageColumn>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm" style={{ color: "var(--ui-content-secondary)" }}>
          {active} active · {rules.length - active} shadow
        </span>
        <span className="ml-auto">
          <Button variant="primary" onClick={() => openDrawer(null)}>
            New rule
          </Button>
        </span>
      </div>
      {rulesP.stale ? <ScopeLine>Showing last good copy</ScopeLine> : null}
      <NoticeRow title="Hard-stop floor —" tone="fail">
        never auto-applied, not declarable.
      </NoticeRow>
      <GroupedList>
        {HARD_STOP_CLASSES.map((label) => (
          <Row key={label} label={label} />
        ))}
      </GroupedList>

      {SCOPES.map(([scope, label]) => {
        const mine = rules.filter((r) => r.scope === scope);
        return (
          <section key={scope}>
            <BandHead label={label} count={mine.length} />
            {!mine.length ? (
              <ScopeLine>No rules in this scope.</ScopeLine>
            ) : (
              <RuleTable label={label} rules={mine} onOpen={openDrawer} />
            )}
          </section>
        );
      })}

      {drawer && regP.data ? (
        <RuleDrawer
          key={drawer.rule?.id ?? "new"}
          rule={drawer.rule}
          reg={regP.data}
          onClose={() => setDrawer(null)}
        />
      ) : null}
    </PageColumn>
  );
}
