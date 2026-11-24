// Headless exercise of the mock store: the full decision
// loop and every other stateful control, driven against a
// manual scenario clock. Run: npm run exercise (bun).
// Exit 1 on any failed assertion.

import { createMockAttentionStore, manualClock } from "../src/attention/store";

let failures = 0;
function check(ok: boolean, label: string, detail = ""): void {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
}
function eq<T>(actual: T, expected: T, label: string): void {
  check(Object.is(actual, expected), label, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

const clock = manualClock();
const ds = createMockAttentionStore(clock);

// ---------- initial state: the seeded stall has returned ----------
{
  const today = ds.getToday();
  eq(today.decision_count, 7, "initial decision count (badge) — decisions + the breakthrough");
  eq(today.breakthrough.length, 1, "initial breakthrough band");
  eq(today.awaiting.length, 0, "awaiting band empty at load — the stalled item already returned");
  const rig9 = today.decisions.find((i) => i.id === "@beacon:rig-9-renewal");
  check(!!rig9, "stalled rig-9 item is back in the queue");
  eq(rig9?.history.length, 1, "rig-9 carries its stalled decision in history");
  eq(rig9?.history[0]?.outcome, "stalled", "rig-9 history outcome is stalled");
  check(!!rig9?.failure && rig9.failure.includes("120 min"), "rig-9 failure is on its face", rig9?.failure ?? "");
  eq(today.fyi.count, 4, "FYI rollup excludes main's muted heartbeat item");

  const glance = ds.getGlance();
  eq(glance.count, 7, "glance count agrees with Today");
  eq(glance.count_label, "7 need you", "glance count label");
  eq(glance.sub_label, "decisions waiting · oldest 2 h 24 min", "glance oldest-waiting sub (the returned rig-9 item)");
  eq(glance.next.length, 2, "glance Next holds two items");

  const handlers = ds.getHandlers();
  eq(handlers.subtitle, "6 handlers · 7 decisions waiting", "handlers subtitle");
  const programmes = ds.getProgrammes();
  eq(programmes.find((p) => p.slug === "northwind-cutover")?.open_decisions, 3, "northwind card: 3 open decisions");
  eq(programmes.find((p) => p.slug === "kite-freight")?.open_decisions, 2, "kite-freight card: breakthrough + returned renewal");

  const digest = ds.getDigest();
  eq(digest.next_label, "Today · Midday", "digest next window label");
  eq(digest.next_detail, "3:00 PM · in 56 min", "digest next window detail");
  // One waiting count, every surface (D5): the badge
  // count, the digest will-include count and the
  // per-handler sum are the same number or this fails.
  const digestDecisions = Number(digest.preview_label.match(/(\d+) decisions/)?.[1]);
  eq(digestDecisions, today.decision_count, "digest will-include count agrees with the badge count");
  const perHandlerSum = handlers.rows.reduce(
    (n, r) => n + Number(r.trailing?.label.match(/^(\d+) waiting$/)?.[1] ?? 0),
    0,
  );
  eq(perHandlerSum, today.decision_count, "per-handler waiting sum agrees with the badge count");
  eq(glance.count, today.decision_count, "glance count agrees with the badge count");

  // Programme lane blocks (lane-records plan, Step 2):
  // the specimens ride the seed in the served shape.
  const blocks = digest.content.programme_lanes;
  const quarry = blocks.find((b) => b.slug === "quarry-index");
  eq(quarry?.actual, 2, "full staffing: quarry actual counts both lanes");
  eq(quarry?.expected, 2, "full staffing: quarry expected is the queue count");
  eq(quarry?.queue_unstaffed.length, 0, "full staffing: nothing unstaffed — the row reads clear");
  eq(
    quarry?.lanes.some((l) => l.venue === "none" && !l.stale),
    true,
    "full staffing: the venue-none authoring lane is served and counted",
  );
  const cedar = blocks.find((b) => b.slug === "cedar-billing");
  eq(cedar?.actual, 1, "one short: cedar actual counts only the fresh lane");
  eq(cedar?.expected, 3, "one short: cedar expected is the queue count");
  eq(
    cedar?.queue_unstaffed.map((i) => i.key).join(","),
    "ledger-reconcile,statements-export",
    "one short: queue_unstaffed names the unstaffed items",
  );
  eq(
    cedar?.lanes.find((l) => l.key === "ledger-reconcile")?.stale,
    true,
    "stale lane: served flagged stale, excluded from actual",
  );
  eq(
    blocks.some((b) => b.slug === "northwind-cutover"),
    false,
    "no named queue: northwind carries no block and renders no row",
  );
  eq(
    blocks.some((b) => b.slug === "kite-freight"),
    false,
    "no named queue: kite-freight carries no block and renders no row",
  );
}

// ---------- the fulfilled loop: decide -> queued -> sent -> fulfilled ----------
{
  const sendsBefore = ds.getSends().length;
  const r1 = ds.decide("main:northwind-rehearsal", { verb: "decide", option_id: "go", note: "Proceed", idempotency_key: "k1" });
  check(r1.ok, "decide northwind (option: go) accepted");
  eq(ds.getSends().length, sendsBefore + 1, "main's decision mints a single send (no copy — ATT3)");

  const r2 = ds.decide("@tally:reparse-cadence", { verb: "done", idempotency_key: "k2" });
  check(r2.ok, "decide tally (done) accepted");
  eq(ds.getSends().length, sendsBefore + 3, "tally's decision mints primary + main copy (ATT3)");

  let today = ds.getToday();
  eq(today.decision_count, 5, "decision count drops by two everywhere");
  eq(today.awaiting.length, 2, "both decided items are in the awaiting band");
  eq(today.awaiting.find((i) => i.id === "main:northwind-rehearsal")?.band_state, "queued", "northwind band state: queued");

  ds.tick(); // consumer claims the oldest queued send
  today = ds.getToday();
  eq(today.awaiting.find((i) => i.id === "main:northwind-rehearsal")?.band_state, "sent", "after one pass: northwind sent (claimed)");
  eq(today.awaiting.find((i) => i.id === "@tally:reparse-cadence")?.band_state, "queued", "tally still queued behind it (settle-first order)");

  ds.tick(); // settle: northwind delivered; tally claimed
  today = ds.getToday();
  check(!today.awaiting.some((i) => i.id === "main:northwind-rehearsal"), "northwind cleared the band");
  eq(ds.getSends().find((s) => s.id === "s0008")?.outcome, "delivered", "northwind's send delivered (fulfillment is per-item; no ledger is served)");
  eq(today.awaiting.find((i) => i.id === "@tally:reparse-cadence")?.band_state, "sent", "tally now sent");

  ds.tick(); // settle tally; claim the copy
  ds.tick(); // settle the copy
  today = ds.getToday();
  check(!today.awaiting.some((i) => i.id === "@tally:reparse-cadence"), "tally fulfilled — cleared the band");
  eq(ds.getSends().find((s) => s.id === "s0010")?.outcome, "delivered", "the main copy delivered independently");
  eq(ds.getProgrammes().find((p) => p.slug === "northwind-cutover")?.open_decisions, 2, "northwind card drops to 2");
  eq(ds.getGlance().count, 5, "glance count agrees after fulfillment");
}

// ---------- the failed loop: decide -> sent -> failed -> returned ----------
{
  const r = ds.decide("@quarry:index-window", { verb: "approve", idempotency_key: "k3" });
  check(r.ok, "decide quarry (approve) accepted");
  ds.tick(); // claim the primary
  let today = ds.getToday();
  eq(today.awaiting.find((i) => i.id === "@quarry:index-window")?.band_state, "sent", "quarry decision sent");
  ds.tick(); // settle: the mock transport fails thread-quarry
  today = ds.getToday();
  check(!today.awaiting.some((i) => i.id === "@quarry:index-window"), "quarry decision left the band");
  const back = today.decisions.find((i) => i.id === "@quarry:index-window");
  check(!!back, "quarry item returned to the queue");
  eq(back?.history.length, 1, "returned with one history entry");
  eq(back?.history[0]?.outcome, "failed", "history outcome is failed");
  check(!!back?.failure && back.failure.includes("target thread unreachable"), "failure visible on the item's face", back?.failure ?? "");
  ds.tick();
  ds.tick(); // the main copy claims + delivers; the item is untouched
  today = ds.getToday();
  eq(today.decisions.find((i) => i.id === "@quarry:index-window")?.history.length, 1, "copy delivery does not touch the returned item");
}

// ---------- replay guards ----------
{
  const first = ds.decide("@beacon:rig-9-renewal", { verb: "renew", idempotency_key: "k4" });
  check(first.ok && !first.replayed, "rig-9 re-decided after its return");
  const sendsAfterFirst = ds.getSends().length;
  const sameKey = ds.decide("@beacon:rig-9-renewal", { verb: "renew", idempotency_key: "k4" });
  check(sameKey.ok && sameKey.decision?.send_id === (first.ok ? first.decision.send_id : null), "same idempotency key returns the standing decision");
  eq(ds.getSends().length, sendsAfterFirst, "same-key replay mints nothing");
  const newKey = ds.decide("@beacon:rig-9-renewal", { verb: "renew", idempotency_key: "k5" });
  check(newKey.ok && newKey.replayed, "repeated tap on a standing decision reports replayed");
  eq(ds.getSends().length, sendsAfterFirst, "repeated tap records and sends nothing");
  ds.tick();
  ds.tick();
  check(!ds.getToday().awaiting.some((i) => i.id === "@beacon:rig-9-renewal"), "rig-9 decision fulfills on the second attempt");
  const gone = ds.decide("@beacon:rig-9-renewal", { verb: "renew", idempotency_key: "k6" });
  check(!gone.ok, "a fulfilled decision is never changed — the item is gone, a new one would be needed");
}

// ---------- push-fact fulfillment ----------
{
  const r = ds.decide("@forge:release-push", { verb: "push", idempotency_key: "k7" });
  check(r.ok, "decide forge push accepted");
  eq(ds.getToday().awaiting.find((i) => i.id === "@forge:release-push")?.band_state, "recorded", "push decision sits in the band as recorded");
  ds.tick();
  check(ds.getToday().awaiting.some((i) => i.id === "@forge:release-push"), "push not yet fulfilled — the fact has not flipped");
  ds.tick();
  const today = ds.getToday();
  check(!today.awaiting.some((i) => i.id === "@forge:release-push"), "push decision cleared once measured");
}

// ---------- snooze: recorded, then cleared ----------
{
  const before = ds.getToday().decision_count;
  const r = ds.decide("@forge:nightly-failure", { verb: "snooze", idempotency_key: "k8" });
  check(r.ok, "snooze accepted");
  eq(ds.getSends().length, 14, "snooze mints no send");
  eq(ds.getToday().awaiting.find((i) => i.id === "@forge:nightly-failure")?.band_state, "recorded", "snooze sits in the band as recorded");
  ds.tick();
  const today = ds.getToday();
  check(!today.awaiting.some((i) => i.id === "@forge:nightly-failure"), "snooze clears the band");
  eq(today.decision_count, before - 1, "decision count reflects the snooze");
}

// ---------- validation (fresh store) ----------
{
  const ds2 = createMockAttentionStore(manualClock());
  const noOption = ds2.decide("main:northwind-rehearsal", { verb: "decide", idempotency_key: "v1" });
  check(!noOption.ok && noOption.error.includes("option required"), "decide without an option is refused", noOption.ok ? "" : noOption.error);
  const verbWithOption = ds2.decide("main:northwind-rehearsal", { verb: "snooze", option_id: "go", idempotency_key: "v2" });
  check(!verbWithOption.ok, "an option on a non-decide verb is refused");
  const unserved = ds2.decide("@beacon:rig-12-lease", { verb: "done", idempotency_key: "v3" });
  check(!unserved.ok && unserved.error.includes("not served"), "a verb outside the served set is refused", unserved.ok ? "" : unserved.error);
  eq(ds2.getSends().length, 7, "refused decisions mint nothing");
  eq(ds2.getToday().decision_count, 7, "refused decisions change nothing");
}

// ---------- stall by clock (fresh store) ----------
{
  const c3 = manualClock();
  const ds3 = createMockAttentionStore(c3);
  const r = ds3.decide("@tally:reparse-cadence", { verb: "done", idempotency_key: "s1" });
  check(r.ok, "stall store: decision accepted");
  c3.advance(121 * 60_000);
  ds3.tick();
  const back = ds3.getToday().decisions.find((i) => i.id === "@tally:reparse-cadence");
  check(!!back, "unfulfilled past 120 min returns to the queue");
  eq(back?.history[0]?.outcome, "stalled", "return outcome is stalled");
}

// ---------- presence: filtering + read-time expiry ----------
{
  ds.setPresence("away", "tomorrow-08:00");
  let presence = ds.getPresence();
  eq(presence.mode, "away", "presence set to away");
  eq(presence.chip_label, "Away · until 8:00 AM", "presence chip label");
  const glance = ds.getGlance();
  eq(glance.count, 1, "away glance counts breakthroughs only");
  eq(glance.next.length, 1, "away glance lists the breakthrough");
  eq(glance.next[0]?.kind, "breakthrough", "away glance next is the breakthrough");
  eq(glance.rows.length, 1, "away glance withholds next-due rows");
  check(ds.getToday().decision_count > 0, "the decision queue is never presence-filtered");

  ds.setPresence("focus", "1h");
  eq(ds.getGlance().sub_label, "Only breakthroughs and decisions", "focus glance carries the expectation");
  clock.advance(61 * 60_000);
  presence = ds.getPresence();
  eq(presence.mode, "active", "expired presence serves as active at read time");
  ds.setPresence("active", "17:00");
  eq(ds.getPresence().chip_label, "Active · until 5:00 PM", "presence restored for the digest checks");
}

// ---------- digest windows + include ----------
{
  // Scenario clock is now 15:05 after the presence advance:
  // midday (15:00) has passed, evening is disabled, so the
  // next window is tomorrow's Morning.
  let digest = ds.getDigest();
  eq(digest.next_label, "Tomorrow · Morning", "next window rolls to tomorrow once midday passes");
  ds.setDigestWindow("evening", true);
  digest = ds.getDigest();
  eq(digest.next_label, "Today · Evening", "enabling evening makes it the next window");
  check(digest.preview_label.startsWith("Will include:"), "digest preview composes", digest.preview_label);
  ds.setDigestInclude("decisions", false);
  ds.setDigestInclude("waiting", false);
  ds.setDigestInclude("fyi", false);
  eq(ds.getDigest().preview_label, "Will include: nothing — all sections off", "all includes off reads honestly");
}

// ---------- muted types move the FYI rollup ----------
{
  eq(ds.getToday().fyi.count, 4, "FYI count before unmuting");
  ds.setMutedType("main", "Heartbeat notices", false);
  eq(ds.getToday().fyi.count, 5, "unmuting surfaces the held FYI item");
  eq(ds.getToday().fyi.newest_title, "Northwind rehearsal notes posted", "the unmuted item is the newest");
  ds.setMutedType("main", "Heartbeat notices", true);
  eq(ds.getToday().fyi.count, 4, "re-muting holds it again");
}

// ---------- shadow sends never dispatch ----------
{
  const shadow = ds.getSends().find((s) => s.id === "s0005");
  eq(shadow?.mode, "shadow", "seeded shadow send present");
  eq(shadow?.dispatch.consumer, null, "shadow send was never claimed");
  eq(shadow?.outcome, "recorded", "shadow send never delivered");
}

// ---------- A3: the digest carries its content (fresh store) ----------
{
  const ds6 = createMockAttentionStore(manualClock());
  const content = ds6.getDigest().content;
  eq(content.sections.map((s) => s.kind).join(","), "push_needed,improvement,performance", "digest sections in the served order");
  eq(content.sections[0]?.kind_label, "Push needed", "section kind label composed from the registry");
  eq(content.sections[0]?.owner_label, "Waiting on you", "section owner label composed");
  eq(content.sections[0]?.rows[0]?.handler_label, "Forge", "section row handler label resolves");
  eq(content.sections[0]?.rows[0]?.provenance_label, "Agent offer — awaiting your tap", "section row provenance label composed");
  eq(content.stalls.length, 1, "exactly one derived stall at the scenario start");
  eq(content.stalls[0]?.handle, "@beacon", "the stall is the owner-blocked lane past the threshold");
  eq(content.stalls[0]?.status_label, "Blocked — owner", "stall status label composed");
  eq(content.stalls[0]?.clearing_act, "Rule on the rig-9 renewal", "stall carries its clearing act");
  check((content.stalls[0]?.age_hours ?? 0) > 6, "stall age is past the 6 h threshold", String(content.stalls[0]?.age_hours));
  eq(content.staffing.available, true, "staffing measure available");
  eq(content.staffing.idle_minutes_total, 74, "staffing idle minutes served");
  eq(content.staffing.rows[0]?.kind_label, "Owner waiting", "staffing row kind label composed");
  eq(content.staffing.rows[0]?.handler_label, "Beacon", "staffing row handler label resolves");
  eq(content.staffing.rows[1]?.escalation_label, "Escalated to Main", "escalated staffing row reads so");
  const beaconTopic = content.topics.find((t) => t.topic === "beacon");
  eq(beaconTopic?.stalls, 1, "beacon topic counts its stall");
  eq(beaconTopic?.worst_label, "Blocked — owner", "beacon topic worst status");
  eq(beaconTopic?.open_counts.find((c) => c.kind === "decision")?.count, 1, "beacon topic open decision count");
  eq(beaconTopic?.open_counts.find((c) => c.kind === "breakthrough")?.count, 1, "beacon topic open breakthrough count");
  eq(beaconTopic?.lanes[0]?.quick_verbs.map((v) => v.verb).join(","), "park,leave_it", "blocked lane quick verbs ride the topic");
  const forgeTopic = content.topics.find((t) => t.topic === "forge");
  eq(forgeTopic?.lanes[0]?.quick_verbs.map((v) => v.verb).join(","), "accept_review,reject_incomplete,leave_it", "review lane quick verbs ride the topic");
  eq(content.parked_plans.available, true, "parked plans available");
  eq(content.parked_plans.plans.length, 2, "two parked plans served");
  eq(content.parked_plans.plans[0]?.age_label, "waiting 6 days", "parked plan age label composed");
}

// ---------- A1: handler steering (fresh store) ----------
{
  const ds4 = createMockAttentionStore(manualClock());
  const forge = ds4.getHandlerDetail("@forge");
  eq(forge?.status?.status_code, "REVIEW", "forge status served");
  eq(forge?.status?.status_label, "Review", "status label composed from the registry");
  eq(forge?.status?.quick_verbs.map((v) => v.verb).join(","), "accept_review,reject_incomplete,leave_it", "review status quick verbs");
  eq(forge?.handler_verbs.length, 9, "all nine handler verbs served when none ride the status");
  eq(forge?.handler_verbs[0]?.label, "Status ping", "handler verb labels composed");
  const main = ds4.getHandlerDetail("main");
  eq(main?.status?.quick_verbs.map((v) => v.verb).join(","), "park,leave_it", "working status quick verbs");
  check(!main?.handler_verbs.some((v) => v.verb === "park"), "a verb rides exactly one surface — park is not in main's steering row");

  const pingsBefore = ds4.getSends().filter((s) => s.template.startsWith("status-ping")).length;
  const ping = ds4.handlerAction("@forge", "status_ping", "a1");
  check(ping.ok, "status ping accepted");
  const pingSends = ds4.getSends().filter((s) => s.template.startsWith("status-ping"));
  eq(pingSends.length, pingsBefore + 1, "the ping mints its send");
  check(pingSends[pingSends.length - 1]?.text.startsWith("Status ping — the owner asks"), "ping text renders the served template", pingSends[pingSends.length - 1]?.text ?? "");
  const pingAgain = ds4.handlerAction("@forge", "status_ping", "a2");
  check(!pingAgain.ok && pingAgain.error.includes("already went out this digest window"), "a second ping inside the window is a conflict", pingAgain.ok ? "" : pingAgain.error);
  eq(ds4.getSends().filter((s) => s.template.startsWith("status-ping")).length, pingsBefore + 1, "the conflicted ping mints nothing");
  const pingReplay = ds4.handlerAction("@forge", "status_ping", "a1");
  check(pingReplay.ok && pingReplay.action_id === (ping.ok ? ping.action_id : ""), "a replayed key returns the standing act");
  eq(ds4.getHandlerDetail("@forge")?.owner_actions.length, 1, "one owner action recorded for the forge");
  eq(ds4.getHandlerDetail("@forge")?.owner_actions[0]?.verb_label, "Status ping", "owner action speaks its label");

  const par = ds4.handlerAction("@tally", "parallelize", "a3");
  check(par.ok, "parallelize accepted");
  eq(ds4.getSends().filter((s) => s.template === "parallelize").length, 1, "parallelize mints its send");

  const sableBefore = ds4.getHandlerDetail("@sable")?.open_items.length ?? -1;
  eq(sableBefore, 0, "sable has no open items before the commission");
  const pass = ds4.handlerAction("@sable", "critic_pass", "a4");
  check(pass.ok, "critic pass accepted");
  const sableAfter = ds4.getHandlerDetail("@sable");
  eq(sableAfter?.open_items.length, 1, "the pass commission lands as an open item");
  eq(sableAfter?.open_items[0]?.kind, "action", "the commission item kind is action");
  eq(sableAfter?.open_items[0]?.title, "Critic pass — Sable", "the commission item title");
  eq(ds4.getSends().filter((s) => s.template === "commission").length, 1, "the commission mints its send");
  const commissionId = sableAfter?.open_items[0]?.id ?? "";
  const clearPass = ds4.decide(commissionId, { verb: "done", idempotency_key: "a5" });
  check(clearPass.ok, "the commission item is decidable like any item");
  eq(ds4.getHandlerDetail("@sable")?.open_items.length, 0, "the decided commission leaves the open list");

  const park = ds4.handlerAction("@tally", "park", "a6");
  check(park.ok, "park accepted");
  eq(ds4.getHandlerDetail("@tally")?.status?.status_code, "WORKING", "the answering post has not landed before the tick");
  ds4.tick();
  eq(ds4.getHandlerDetail("@tally")?.status?.status_code, "PARKED", "the lane's answering post lands on the tick");
  eq(ds4.getHandlerDetail("@tally")?.status?.quick_verbs.map((v) => v.verb).join(","), "leave_it", "a parked status serves only leave_it");

  const sendsBeforeLeave = ds4.getSends().length;
  const leave = ds4.handlerAction("@quarry", "leave_it", "a9");
  check(leave.ok, "leave_it accepted");
  eq(ds4.getSends().length, sendsBeforeLeave, "leave_it sends nothing");
  eq(ds4.getHandlerDetail("@quarry")?.owner_actions.length, 1, "leave_it is still recorded");

  const unserved = ds4.handlerAction("@forge", "explode", "a7");
  check(!unserved.ok && unserved.error.includes("not served"), "an unserved verb is refused", unserved.ok ? "" : unserved.error);
  const unknown = ds4.handlerAction("@nobody", "park", "a8");
  check(!unknown.ok && unknown.error.includes("No such handler"), "an unknown handler is refused", unknown.ok ? "" : unknown.error);
}

// ---------- A2: rules management (fresh store) ----------
{
  const ds5 = createMockAttentionStore(manualClock());
  const registries = ds5.getRegistries();
  eq(registries.status_codes.length, 8, "registries serve the status codes");
  eq(registries.wait_classes.find((c) => c.name === "permission_card")?.hard_stop, true, "hard-stop classes are flagged in the registry");
  eq(registries.wait_classes.find((c) => c.name === "program_step")?.label, "Program step", "class labels composed");
  check(registries.templates.some((t) => t.kind === "status-request"), "templates served for the editor's pickers");

  const rules = ds5.getRules();
  eq(rules.length, 5, "five seeded rules served");
  eq(rules[0]?.id, "settled-continues", "rules serve in priority order");
  eq(rules[0]?.when_label, "Wait — class is Settled continue · with all flags holding", "when sentence composed");
  eq(rules[0]?.then_label, "Post, then auto-apply · continue-settled · cooldown 30m", "then sentence composed");
  eq(rules.find((r) => r.id === "away-holds-decisions")?.display_name, "Away Holds Decisions", "display name falls back to the title-cased id");
  const aged = rules.find((r) => r.id === "aged-program-steps-nudge");
  check(!!aged?.when_label.includes("after 240 min") && aged.when_label.includes("+ conditions"), "aged rule when sentence carries trigger + conditions", aged?.when_label ?? "");
  check(!!aged?.then_label.includes("escalate after 2 → Main"), "aged rule then sentence carries its guards", aged?.then_label ?? "");

  const candidate = {
    id: "tally-program-steps",
    name: null,
    match: { wait_class: "program_step", status_code: null, kind: null, handle: "@tally" },
    where: null,
    action: { type: "post", template: "status-request" },
    scope: "always",
    requires: [],
    priority: 90,
    on_scope_miss: "pending",
    trigger: { on: "on_enter" },
    guards: {},
    mode: "shadow",
  } as const;
  const preview = ds5.previewRule({ ...candidate, match: { ...candidate.match }, action: { ...candidate.action }, trigger: { ...candidate.trigger }, guards: {}, requires: [] });
  check(preview.ok, "preview runs on a valid candidate");
  eq(preview.ok ? preview.would_fire.length : -1, 1, "the candidate would fire on exactly one open wait");
  eq(preview.ok ? preview.would_fire[0]?.wait_id : "", "w0003", "the firing wait is tally's program step");
  check(preview.ok && (preview.would_fire[0]?.text ?? "").startsWith("Status request — Cedar billing"), "the preview renders the post text", preview.ok ? (preview.would_fire[0]?.text ?? "") : "");
  eq(ds5.getSends().length, 7, "a preview sends nothing");
  eq(ds5.getToday().awaiting.length, 0, "a preview decides nothing");

  const saved = ds5.saveRule({ ...candidate, match: { ...candidate.match }, action: { ...candidate.action }, trigger: { ...candidate.trigger }, guards: {}, requires: [] });
  check(saved.ok, "the candidate saves");
  eq(ds5.getRules().length, 6, "the saved rule joins the served set");
  eq(ds5.getRules().find((r) => r.id === "tally-program-steps")?.display_name, "Tally Program Steps", "the saved rule's display name composes");
  const reprioritized = ds5.saveRule({ ...candidate, match: { ...candidate.match }, action: { ...candidate.action }, trigger: { ...candidate.trigger }, guards: {}, requires: [], priority: 5 });
  check(reprioritized.ok, "saving the same id replaces");
  eq(ds5.getRules().length, 6, "a replace does not duplicate");
  eq(ds5.getRules()[0]?.id, "tally-program-steps", "the replaced rule re-sorts by its new priority");

  const noMatch = ds5.previewRule({
    id: "venue-questions",
    name: null,
    match: { wait_class: "venue_question", status_code: null, kind: null, handle: null },
    where: null,
    action: { type: "surface" },
    scope: "always",
    requires: [],
    priority: 100,
    on_scope_miss: "pending",
    trigger: { on: "on_enter" },
    guards: {},
    mode: "shadow",
  });
  check(noMatch.ok && noMatch.would_fire.length === 0, "a rule matching no open wait previews empty");

  const floorBreach = ds5.saveRule({
    id: "cards-auto",
    name: null,
    match: { wait_class: "permission_card", status_code: null, kind: null, handle: null },
    where: null,
    action: { type: "auto_apply" },
    scope: "always",
    requires: [],
    priority: 100,
    on_scope_miss: "pending",
    trigger: { on: "on_enter" },
    guards: {},
    mode: "active",
  });
  check(!floorBreach.ok && floorBreach.error.includes("hard-stop classes may not be applied"), "the floor refuses an applying rule on a hard-stop class", floorBreach.ok ? "" : floorBreach.error);
  const unknownClass = ds5.saveRule({
    id: "nope",
    name: null,
    match: { wait_class: "not_a_class", status_code: null, kind: null, handle: null },
    where: null,
    action: { type: "surface" },
    scope: "always",
    requires: [],
    priority: 100,
    on_scope_miss: "pending",
    trigger: { on: "on_enter" },
    guards: {},
    mode: "shadow",
  });
  check(!unknownClass.ok && unknownClass.error.includes("unregistered class"), "an unregistered class is refused", unknownClass.ok ? "" : unknownClass.error);
  eq(ds5.getRules().length, 6, "refused saves store nothing");
}

// ---------- A5: snooze carries its payload (fresh store) ----------
{
  const ds6 = createMockAttentionStore(manualClock());
  const item = ds6.getToday().decisions.find((i) => i.id === "@forge:nightly-failure");
  check(!!item, "A5: nightly-failure is in the queue");
  eq(item?.snooze_options.times.length, 2, "A5: two snooze times are served");
  eq(item?.snooze_options.on_activity, true, "A5: return-on-activity is served");
  const second = item?.snooze_options.times[1];
  const badTime = ds6.decide("@forge:nightly-failure", {
    verb: "snooze",
    return_at: "2027-01-01T00:00:00.000Z",
    idempotency_key: "a5-bad",
  });
  check(!badTime.ok && badTime.error.includes("not one of the served times"), "A5: an unserved return time is refused", badTime.ok ? "" : badTime.error);
  const sendsBefore = ds6.getSends().length;
  const r = ds6.decide("@forge:nightly-failure", {
    verb: "snooze",
    return_at: second?.at,
    return_on_activity: false,
    resume_note: "Check the pack log first",
    idempotency_key: "a5-1",
  });
  check(r.ok, "A5: a snooze with a chosen time is accepted");
  eq(ds6.getSends().length, sendsBefore, "A5: a snooze mints no send");
  const awaiting = ds6.getToday().awaiting.find((i) => i.id === "@forge:nightly-failure");
  check(!!awaiting && awaiting.decided_label.includes(second?.label ?? "￿"), "A5: the awaiting label names the chosen return time", awaiting?.decided_label);
  check(!!awaiting && !awaiting.decided_label.includes("or on new activity"), "A5: activity off stays off the label", awaiting?.decided_label);
  check(!!awaiting && awaiting.decided_label.includes("Check the pack log first"), "A5: the resume note rides the label", awaiting?.decided_label);
  ds6.tick();
  check(!ds6.getToday().awaiting.some((i) => i.id === "@forge:nightly-failure"), "A5: the snooze fulfills and clears the band");
}

// ---------- A6: the learning loop (fresh store) ----------
{
  const ds7 = createMockAttentionStore(manualClock());
  const decidedIds: string[] = [];
  const commissionContinue = (handle: string, tag: string): boolean => {
    const act = ds7.handlerAction(handle, "critic_pass", `${tag}-c`);
    if (!act.ok) return false;
    const open = ds7.getHandlerDetail(handle)?.open_items ?? [];
    const item = open.find((i) => i.kind === "action" && !decidedIds.includes(i.id));
    if (!item) return false;
    decidedIds.push(item.id);
    return ds7.decide(item.id, { verb: "continue", idempotency_key: `${tag}-d` }).ok;
  };
  // Three identical counted taps on one handler surface a proposal.
  for (let n = 1; n <= 3; n += 1) {
    check(commissionContinue("@sable", `a6-s${n}`), `A6: sable continue tap ${n} lands`);
    eq(
      ds7.getToday().decisions.filter((i) => i.kind === "rule_proposal").length,
      n < 3 ? 0 : 1,
      `A6: proposal count after tap ${n}`,
    );
  }
  const proposal = ds7.getToday().decisions.find((i) => i.kind === "rule_proposal");
  check(!!proposal?.title.includes("3 times"), "A6: the proposal speaks the backend's title", proposal?.title);
  eq(proposal?.proposal?.verb, "continue", "A6: the proposal carries its verb");
  eq(proposal?.proposal?.cls, "action", "A6: the proposal counts under the item kind (no wait behind it)");
  eq(proposal?.clears_at_source, false, "A6: a proposal does not clear at the source");
  eq(proposal?.verbs.join(","), "accept_proposal,reject_proposal", "A6: the proposal serves its two verdicts");
  // Accepting creates the shadow rule and clears the item.
  const accept = ds7.decide(proposal?.id ?? "", { verb: "accept_proposal", idempotency_key: "a6-accept" });
  check(accept.ok, "A6: accept_proposal accepted");
  eq(ds7.getActionRules().length, 1, "A6: one action rule stands");
  eq(ds7.getActionRules()[0]?.mode, "shadow", "A6: the proposal's rule is shadow");
  eq(ds7.getActionRules()[0]?.verb, "continue", "A6: the rule carries the tapped verb");
  eq(ds7.getActionRules()[0]?.created_from, "proposal", "A6: the rule names its origin");
  ds7.tick();
  check(!ds7.getToday().decisions.some((i) => i.id === proposal?.id), "A6: the accepted proposal clears");
  // The next commission on that handler carries the shadow hint.
  check(ds7.handlerAction("@sable", "critic_pass", "a6-hint-c").ok, "A6: hint commission accepted");
  const hinted = (ds7.getHandlerDetail("@sable")?.open_items ?? []).find(
    (i) => i.kind === "action" && !decidedIds.includes(i.id),
  );
  check(!!hinted?.rule_hint && hinted.rule_hint.includes("shadow rule"), "A6: a matching item carries the shadow hint", hinted?.rule_hint ?? "");
  // A second pattern, rejected: the count resets, no rule stands.
  for (let n = 1; n <= 3; n += 1) {
    check(commissionContinue("@quarry", `a6-q${n}`), `A6: quarry continue tap ${n} lands`);
  }
  const proposal2 = ds7.getToday().decisions.find((i) => i.kind === "rule_proposal");
  check(!!proposal2, "A6: the second pattern proposes too");
  const reject = ds7.decide(proposal2?.id ?? "", { verb: "reject_proposal", idempotency_key: "a6-reject" });
  check(reject.ok, "A6: reject_proposal accepted");
  eq(ds7.getActionRules().length, 1, "A6: a rejection creates no rule");
  ds7.tick();
  check(!ds7.getToday().decisions.some((i) => i.id === proposal2?.id), "A6: the rejected proposal clears");
}

// ---------- A6: rule_it / approve_rule / make_rule (fresh store) ----------
{
  const ds8 = createMockAttentionStore(manualClock());
  const noOpt = ds8.decide("main:northwind-rehearsal", { verb: "rule_it", idempotency_key: "a6-r0" });
  check(!noOpt.ok && noOpt.error.includes("option required"), "A6: rule_it without an option is refused", noOpt.ok ? "" : noOpt.error);
  const ruled = ds8.decide("main:northwind-rehearsal", { verb: "rule_it", option_id: "go", idempotency_key: "a6-r1" });
  check(ruled.ok, "A6: rule_it with an option is accepted");
  eq(ruled.ok ? ruled.decision.verb : "", "rule_it", "A6: the decision records rule_it");
  eq(ds8.getActionRules().length, 1, "A6: rule_it creates one rule");
  eq(ds8.getActionRules()[0]?.created_from, "rule_it", "A6: the rule_it rule names its origin");
  eq(ds8.getActionRules()[0]?.mode, "shadow", "A6: the rule_it rule is shadow");
  eq(ds8.getActionRules()[0]?.verb, "decide", "A6: the rule_it rule carries the pick");

  const conflict = ds8.decide("@quarry:index-window", { verb: "approve_rule", make_rule: true, idempotency_key: "a6-m0" });
  check(!conflict.ok && conflict.error.includes("already promotes"), "A6: make_rule with approve_rule is refused", conflict.ok ? "" : conflict.error);
  const approved = ds8.decide("@quarry:index-window", { verb: "approve_rule", idempotency_key: "a6-m1" });
  check(approved.ok, "A6: approve_rule accepted");
  eq(approved.ok ? approved.decision.verb : "", "approve", "A6: approve_rule lands as the approval itself");
  eq(ds8.getActionRules().length, 2, "A6: approve_rule adds its rule");
  eq(ds8.getActionRules()[1]?.mode, "active", "A6: the approve_rule rule is active");
  eq(ds8.getActionRules()[1]?.created_from, "approve_rule", "A6: the approve_rule rule names its origin");

  const pushed = ds8.decide("@forge:release-push", { verb: "push", make_rule: true, idempotency_key: "a6-m2" });
  check(pushed.ok, "A6: push with make_rule accepted");
  eq(ds8.getActionRules().length, 3, "A6: make_rule adds a third rule");
  eq(ds8.getActionRules()[2]?.mode, "shadow", "A6: a wait-less make_rule stands in shadow");
  eq(ds8.getActionRules()[2]?.verb, "push", "A6: the make_rule rule carries the tapped verb");
  eq(ds8.getActionRules()[2]?.created_from, "make_rule", "A6: the make_rule rule names its origin");
}

// ---------- A7: mute_type + the clears flag (fresh store) ----------
{
  const ds9 = createMockAttentionStore(manualClock());
  eq(ds9.getToday().fyi.count, 4, "A7: FYI starts at four visible");
  const tallyFyi = ds9.getToday().fyi.items.find((i) => i.id === "@tally:invoice-run-done");
  check(!!tallyFyi, "A7: the tally FYI item is visible");
  eq(tallyFyi?.verbs.join(","), "mute_type", "A7: FYI items serve mute_type");
  const muted = ds9.decide("@tally:invoice-run-done", { verb: "mute_type", idempotency_key: "a7-1" });
  check(muted.ok, "A7: mute_type accepted");
  eq(ds9.getToday().fyi.count, 3, "A7: the muted type leaves the FYI rollup");
  const tallyDetail = ds9.getHandlerDetail("@tally");
  check(
    !!tallyDetail?.muted_types.find((t) => t.type === "Routine run completions" && t.muted),
    "A7: the handler page gains the muted row",
  );
  ds9.setMutedType("@tally", "Routine run completions", false);
  eq(ds9.getToday().fyi.count, 4, "A7: unmuting on the handler page returns the type");
  eq(ds9.getToday().decisions.find((i) => i.id === "@tally:reparse-cadence")?.clears_at_source, false, "A7: reparse-cadence does not clear at the source");
  eq(ds9.getToday().decisions.find((i) => i.id === "@beacon:rig-9-renewal")?.clears_at_source, true, "A7: rig-9 clears at the source");
}

// ---------- A4: vocabulary adds (fresh store) ----------
{
  const dsA = createMockAttentionStore(manualClock());
  eq(dsA.getRegistries().status_codes.length, 8, "A4: eight seeded status codes");
  const badNeed = dsA.addStatusCode({ code: "x", short: "X", label: "X", need: "bogus", terminal: false });
  check(!badNeed.ok && badNeed.error.includes("unknown need"), "A4: an unknown need is refused", badNeed.ok ? "" : badNeed.error);
  const missing = dsA.addStatusCode({ code: "", short: "", label: "", need: "", terminal: false });
  check(!missing.ok && missing.error.includes("code is required"), "A4: a missing code is refused", missing.ok ? "" : missing.error);
  check(dsA.addStatusCode({ code: "waiting_vendor", short: "WV", label: "Waiting on vendor", need: "agent_clearable", terminal: false }).ok, "A4: a status code registers");
  eq(dsA.getRegistries().status_codes.length, 9, "A4: the registry grows");
  const badField = dsA.addField({ name: "eta", type: "funky" });
  check(!badField.ok && badField.error.includes("unknown field type"), "A4: an unknown field type is refused", badField.ok ? "" : badField.error);
  check(dsA.addField({ name: "eta", type: "datetime" }).ok, "A4: a field registers");
  eq(dsA.getRegistries().fields.find((f) => f.name === "eta")?.poster_settable, true, "A4: an added field is poster-settable");
  const hardStop = dsA.addWaitClass({ name: "purchase" });
  check(!hardStop.ok && hardStop.error.includes("hard-stop classes are not editable"), "A4: a hard-stop class is not editable", hardStop.ok ? "" : hardStop.error);
  check(dsA.addWaitClass({ name: "vendor_reply" }).ok, "A4: a wait class registers");
  const vendorRule = dsA.saveRule({
    id: "vendor-rule",
    name: null,
    match: { wait_class: "vendor_reply", status_code: null, kind: null, handle: null },
    where: null,
    action: { type: "surface" },
    scope: "always",
    requires: [],
    priority: 100,
    on_scope_miss: "pending",
    trigger: { on: "on_enter" },
    guards: {},
    mode: "shadow",
  });
  check(vendorRule.ok, "A4: a rule may match the new class at once", vendorRule.ok ? "" : vendorRule.error);
  const badTemplate = dsA.addTemplate({ kind: "k", audience: "everyone", slots: [], text: "hi" });
  check(!badTemplate.ok && badTemplate.error.includes("must be chat or main"), "A4: a bad template audience is refused", badTemplate.ok ? "" : badTemplate.error);
  check(dsA.addTemplate({ kind: "vendor-nudge", audience: "chat", slots: ["name"], text: "Hi {name}" }).ok, "A4: a template registers");
  eq(dsA.getRegistries().templates.find((t) => t.kind === "vendor-nudge")?.version, 1, "A4: a new template is v1");
  check(dsA.addTemplate({ kind: "vendor-nudge", audience: "chat", slots: [], text: "Second text" }).ok, "A4: re-adding a template kind saves");
  eq(dsA.getRegistries().templates.find((t) => t.kind === "vendor-nudge")?.version, 2, "A4: the re-add bumps the version");
  const badKind = dsA.addItemKind({ kind: "milestone", label: "", status_kind: false, digest_owner: null });
  check(!badKind.ok && badKind.error.includes("label is required"), "A4: a kind without a label is refused", badKind.ok ? "" : badKind.error);
  check(dsA.addItemKind({ kind: "milestone", label: "Milestone", status_kind: false, digest_owner: "lane" }).ok, "A4: an item kind registers");
  check(!!dsA.getRegistries().item_kinds.find((k) => k.kind === "milestone"), "A4: the new kind lists");
}

console.log(failures === 0 ? "\nALL EXERCISE CHECKS PASSED" : `\n${failures} EXERCISE CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
