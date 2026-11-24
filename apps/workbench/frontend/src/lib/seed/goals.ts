// Seed goals: the goal records with their contracts,
// pings, and last posts (one closed specimen).

import type { GoalRecord } from "../types";
import type { SeedTime } from "./time";

export function buildGoals(t: SeedTime): GoalRecord[] {
  const { minsAgo, hoursAgo } = t;
  const goals: GoalRecord[] = [
    {
      slug: "workhorse-superapp-build",
      project: "workbench-viewer",
      title: "Workhorse superapp build — supreme-octo-robot",
      shortObjective: "one unified app over one pipeline, on Workhorse Kit v1",
      contract: {
        objective: "Scheduler, workbench, runner, and attention in one unified app over one pipeline, on Workhorse Kit v1.",
        completeWhen: "S0–S11 landed; the four apps live over pipeline feeds; the four source repos archived as they are.",
        blockedOnlyWhen: "A hard stop fires (push, external send, purchase, permission card) or a §10 decision is genuinely unruled.",
        continuation: "Agent-clearable work continues without a tap; the ping measures the record every 15 minutes.",
      },
      ping: { entryId: "goal-ping-workhorse-superapp-build", cadenceMinutes: 15, armed: true },
      lastPost: {
        handle: "@workbench-viewer",
        status_code: "WORKING",
        summary: "S2 kit extraction in flight; four frontend lanes staffed on the frozen contracts",
        refs: { project: "workbench-viewer", plan: "2026-11-12-consolidation-plan", todo_ids: [] },
        ongoing: ["S2 — kit extraction + consumer switch"],
        postedAt: minsAgo(20),
      },
    },
    {
      slug: "document-parsing-successor",
      project: "aldercrest",
      title: "Document-parsing successor",
      contract: {
        objective: "A rules-only successor to the retired taxonomy classifier, with coverage parity as a build step.",
        completeWhen: "Population audit clears the .90/.90 floor per family, or the owner rules adopt / refresh / retire on the audit.",
        blockedOnlyWhen: "A ruling line only the owner can write is missing (the genre cure).",
        continuation: "Lanes continue in parallel; only the ruling-line cure waits.",
      },
      ping: { entryId: "goal-ping-document-parsing-successor", cadenceMinutes: 15, armed: true },
      lastPost: {
        handle: "@aldercrest-data",
        status_code: "BLOCKED-OWNER",
        summary: "Genre defect cure is a ruling line; segment lanes wait on it",
        refs: { project: "aldercrest", plan: "2026-11-11-document-parsing-successor", todo_ids: ["genre-defect-ruling-line-cure"] },
        owner_waiting: { label: "Genre ruling-line cure", commissioned_at: hoursAgo(6) },
        // Contract 11 amendment: a blocked post
        // carries its cited basis + verification stamp. The
        // citation is the owner's escalation the genre cure
        // rides on; main verified it against the owner's
        // traffic and stamped the post.
        basis_citation: { thread: "aldercrest greenfield design thread", at: hoursAgo(6.5) },
        verification: { by: "main", at: hoursAgo(6) },
        postedAt: hoursAgo(2),
      },
    },
    {
      slug: "copperleaf-dag",
      project: "copperleaf",
      title: "Copperleaf v2 — serving DAG",
      contract: {
        objective: "Store-sourced serving for the copperleaf: the DAG complete except Step 6.",
        completeWhen: "Step 6's reparse cadence is ruled and the reparse runs on it.",
        blockedOnlyWhen: "The Step 6 cadence tap — the owner's alone.",
        continuation: "Daily runs continue on the current cadence meanwhile.",
      },
      ping: { entryId: "goal-ping-copperleaf-dag", cadenceMinutes: 60, armed: false },
      lastPost: null,
    },
    {
      // The deployment's real closed goal, seeded at record
      // level from its record (programme closed,
      // 11 of 11 steps landed): the Completed group's specimen.
      slug: "aldercrest-greenfield-tagger",
      project: "aldercrest",
      title: "Aldercrest greenfield tagger successor programme",
      contract: {
        objective: "The rules-only successor to the retired taxonomy classifier, built under the owner's 2026-11-08 retire-and-rebuild approval.",
        completeWhen: "All 11 steps landed, the union tree gated, and the verdict record filed.",
        blockedOnlyWhen: "A family or statement line closing below the .90 audited floor without an owner ruling on named evidence.",
        continuation: "Successors staff immediately on verified completion; milestones, blockers, and the completion verdict only.",
      },
      // A closed record retires its ping: disarmed for good,
      // never re-armed by the toggle.
      ping: { entryId: "goal-ping-aldercrest-greenfield-tagger", cadenceMinutes: 15, armed: false },
      lastPost: {
        handle: "@aldercrest-data",
        status_code: "CLOSED",
        summary: "Programme closed — all 11 steps landed; the verdict record is filed",
        refs: { project: "aldercrest", plan: "2026-11-08-greenfield-tagger-successor", todo_ids: [] },
        postedAt: hoursAgo(3),
      },
    },
  ];
  return goals;
}
