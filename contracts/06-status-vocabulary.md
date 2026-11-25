# 06 — Status vocabulary

**Canonical owners:** the pipeline for the semantics, served
ready; the presentation form (the token status table) is
owned by the Workhorse Kit.

**The contract in one line:** status meaning is defined
once, served ready, and rendered — apps never re-derive a
label, a need, or a terminal flag.

## The two vocabularies

**1. The ruled entry vocabulary + its status table
(VOC1).** SPEC §5.1's ruled vocabulary — canonical /
implemented / deferred / unexplored / hard-gate / abandoned,
changing only via a mutation carrying a ruling note — and
its token status table are **one contract in two files**;
both halves move together or not at all. The table carries
14 named statuses (the six ruled plus stale, needs-changes,
not-covered, approved, in-triage, sent, acknowledged,
done), each `{hue, text{light, dark}, glyph, description}`
on Okabe-Ito hues, plus a 1–7 chart series scale. Fixture:
`fixtures/token-status-table.json` — the verbatim `status`
subtree of the kit's `tokens/tokens.json`. The table's
generation and naming map ride contract 09 (kit
extraction); its semantics ride here.

**2. The task-mode status vocabulary.** The eight codes a
lane posts under (contract 03's status-post form):
WORKING, CONTINUE, REVIEW, DONE, CLOSED, PARKED,
BLOCKED-OWNER, BLOCKED-HARD. As registry data each row is
`{code, label, need, short, terminal}` — fixture:
`fixtures/attention-status-codes.json` (the domain
defaults, exactly as seeded). `need` and `terminal` are
semantics: consumers read them from the served registry,
never from a local copy of the table.

**Served ready, never re-derived.** The scheduler's
centralized `outcome_label()` is the standing instance of
this rule on the run-outcome side (`OK`, `Exit <n> ·
normal`, `Failed · exit <n>`, `Timed out`, `Could not
start` — computed in the backend, rendered by the viewer).
Any label mapping found client-side after consolidation is
a defect against this contract.

## The write surface

The vocabulary registries are owner-extensible at runtime.
Under this contract the `/vocab` write surface **homes in
the pipeline**: vocabulary edits are pipeline registry
writes, and apps stay render-only. Hard-stop wait classes
stay named in code and are **uneditable** through the
surface.

## Contents migrate as data (ATT14)

Vocabulary registry contents — rules, templates (with
versions), status codes, classes, kinds, and action rules
the owner has written at runtime — are **records, not
code**: they migrate as data (verbatim store capture)
and are never re-typed into a tracked file. Row forms, from
the seeded defaults:

- status code: `{code, label, need, short, terminal}`
- template: `{audience, kind, slots[], text, version}` —
  fixture: `fixtures/attention-templates.json` (19 rows,
  including the `decision-reply` row of contract 05)
- wait class: `{name, hard_stop}` — fixture:
  `fixtures/attention-wait-classes.json` (17 seeded rows;
  hard-stop rows are the code-named classes and do
  not arrive through the write surface)

## Preserve clauses carried

VOC1 (the two-file vocabulary contract, whole), ATT14
(registry contents as data).
