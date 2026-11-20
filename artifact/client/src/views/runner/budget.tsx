// Budget — the panel's budget cards, one per (venue,
// account) of the served budget set (FU-2): budgets are per
// venue and per account and are never merged into one mass.
// Each card carries its own balance, today's spend against
// its own daily cap, and the month's against its own monthly
// cap; its cap editor saves against that venue and account
// alone. A budget-less venue (a local machine venue —
// unmetered, unlimited) serves budget: null and renders
// nothing here: no card, no figures, nothing budget-shaped
// (honest absence).
//
// Cap drafts live outside the poll-driven render (the
// panel's rule): each card holds its own draft, keyed by its
// (venue, account), so a portion landing never loses a typed
// cap and one card's editor never touches another's. Blank =
// no cap; caps gate new leases and extensions; a running
// lease is never cut off by a cap change.

import { useState } from "react";
import { Button } from "@workhorse/kit/components/Button";
import { Card } from "@workhorse/kit/components/Card";
import { Field, Input } from "@workhorse/kit/components/Fields";
import { GroupedList, StatRow } from "@workhorse/kit/components/GroupedList";
import { api } from "../../lib/actions";
import {
  capText,
  fmtNum,
  type BudgetCaps,
  type BudgetFigures,
  type BudgetPayload,
} from "./model";
import { DegradedCard, PartStatus } from "./pickers";
import { callApi, useRunner } from "./state";

const CAP_FIELDS = {
  daily: "daily_cu_budget",
  monthly: "monthly_cu_budget",
  standing: "standing_daily_cu_cap",
} as const;

type CapKey = keyof typeof CAP_FIELDS;

interface CardModel {
  key: string;
  title: string;
  sub?: string;
  figures: BudgetFigures;
  /** The caps write's address; absent = the panel's default
   *  target (the legacy single-snapshot card). */
  target?: { venue: string; account: string };
}

/** The cards the served portion renders, from the budget set
 *  of record when it rides the portion; from the snapshot's
 *  own per-account array when it does not; and, for a core
 *  serving neither, the one legacy card over the snapshot's
 *  top-level figures (its primary account's). Budget-less
 *  entries (budget: null) yield no card at all. */
function cardModels(data: BudgetPayload | null): CardModel[] {
  if (!data) return [];
  if (Array.isArray(data.budgets)) {
    const out: CardModel[] = [];
    for (const e of data.budgets) {
      if (e.budget == null) continue;
      out.push({
        key: `${e.venue}:${e.account ?? ""}`,
        title: e.label ?? e.account ?? e.venue,
        sub: e.account ? `${e.venue} · ${e.account}` : e.venue,
        figures: e.budget,
        target: e.account ? { venue: e.venue, account: e.account } : undefined,
      });
    }
    return out;
  }
  const b = data.budget;
  if (!b) return [];
  if (Array.isArray(b.accounts) && b.accounts.length) {
    return b.accounts.map((a) => ({
      key: `${a.venue}:${a.account}`,
      title: a.label,
      sub: `${a.venue} · ${a.account}`,
      figures: {
        balance: a.balance,
        day_spent: a.day_spent,
        month_spent: a.month_spent,
        standing_day_spent: a.standing_day_spent,
        caps: a.caps,
      },
      target: { venue: a.venue, account: a.account },
    }));
  }
  return [{ key: "budget", title: "Budget", figures: b }];
}

function BudgetCard({ model }: { model: CardModel }) {
  const { act, setNotice } = useRunner();
  const [editOpen, setEditOpen] = useState(false);
  const [draft, setDraft] = useState<Record<CapKey, string>>({
    daily: "",
    monthly: "",
    standing: "",
  });

  const b = model.figures;
  const caps: BudgetCaps = b?.caps || {};
  const month = new Date().toLocaleString([], { month: "long" });
  const spent = (val: number | null | undefined, cap: number | null | undefined) =>
    val == null ? "—" : `${fmtNum(val)}${cap != null ? ` of ${fmtNum(cap)}` : ""} CU`;

  const openEditor = () => {
    setDraft({
      daily: caps.daily == null ? "" : String(caps.daily),
      monthly: caps.monthly == null ? "" : String(caps.monthly),
      standing: caps.standing_daily == null ? "" : String(caps.standing_daily),
    });
    setEditOpen(true);
  };

  const save = () => {
    const body: Record<string, unknown> = {};
    if (model.target) {
      body.venue = model.target.venue;
      body.account = model.target.account;
    }
    for (const key of Object.keys(CAP_FIELDS) as CapKey[]) {
      const raw = String(draft[key] ?? "").trim();
      if (raw === "") {
        body[CAP_FIELDS[key]] = null;
        continue;
      }
      const v = Number(raw);
      if (!Number.isFinite(v) || v < 0) {
        setNotice(
          "Caps not saved — each cap must be a non-negative number, or blank for no cap.",
        );
        return;
      }
      body[CAP_FIELDS[key]] = v;
    }
    void act(async () => {
      const res = await callApi<{ caps?: BudgetCaps }>(() =>
        api.setBudget({ body }),
      );
      setEditOpen(false);
      const c = res.caps || {};
      const capsText = `daily ${capText(c.daily)}, monthly ${capText(c.monthly)}, standing ${capText(c.standing_daily)}`;
      setNotice(
        model.target
          ? `Budget caps updated for ${model.title} (${model.target.venue}/${model.target.account}) — ${capsText}`
          : `Budget caps updated — ${capsText}`,
      );
    });
  };

  const capRow = (label: string, key: CapKey) => (
    <Field label={label}>
      {(id) => (
        <Input
          id={id}
          type="number"
          min="0"
          step="0.5"
          placeholder="No cap"
          value={draft[key]}
          onChange={(e) => setDraft((prev) => ({ ...prev, [key]: e.target.value }))}
        />
      )}
    </Field>
  );

  return (
    <Card title={model.title}>
      {model.sub ? (
        <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
          {model.sub}
        </p>
      ) : null}
      <GroupedList>
        <StatRow label="Balance">
          {b?.balance == null ? "—" : `${fmtNum(b.balance)} CU`}
        </StatRow>
        <StatRow label="Today">{spent(b?.day_spent, caps.daily)}</StatRow>
        <StatRow label={month}>{spent(b?.month_spent, caps.monthly)}</StatRow>
      </GroupedList>
      {editOpen ? (
        <div className="mt-4 flex flex-col gap-3">
          {capRow("Daily cap", "daily")}
          {capRow("Monthly cap", "monthly")}
          {capRow("Standing daily cap", "standing")}
          <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
            Blank = no cap.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={save}>Save caps</Button>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-4">
          <Button variant="ghost" onClick={openEditor}>
            Edit caps
          </Button>
        </div>
      )}
    </Card>
  );
}

export function BudgetView() {
  const { parts, allDown } = useRunner();

  if (allDown) return <DegradedCard />;

  const cards = cardModels(parts.budget.data);

  return (
    <div className="flex flex-col gap-4">
      <PartStatus name="budget" part={parts.budget} />
      {cards.map((m) => (
        <BudgetCard key={m.key} model={m} />
      ))}
    </div>
  );
}
