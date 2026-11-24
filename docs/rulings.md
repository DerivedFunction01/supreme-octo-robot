# Standing rulings — the superapp

Standing owner rulings for this repo that outlive any one
plan. The consolidation plan
(`docs/2026-11-12/consolidation-plan.md`) records how the
repo was formed; this file records what governs the app
now.

## 1. Frontend target — one integrated app

The mega repo is ONE app: a single integrated frontend
shell on the unified kit. The four apps (scheduler,
workbench, attention, runner) are views of the one
client — never four separate frontends, never framed
inside a shell, and never each implementing its own
shell or kit. The earlier frame-shell form (a card-picker
shell framing the four apps behind an action relay) is
ruled never-asked-for, and its presence in a tree is a
divergence, not a variant.

## 2. FU-1 — workbench preview is a full page

The workbench preview loads as a FULL PAGE, not a framed
or inset view: a top bar carrying a go-back control and
an info icon. The info icon opens a popup drawer on
mobile and the desktop-appropriate UI on desktop.
Details the ruling does not name follow the unified
kit's patterns. The build is held to the
behaviour-of-record constraint: exhibits fully
interactive, picks persist — a blank or inert page is a
failure. (Mechanism and fallback: the divergence audit,
Addendum 8; approval of the built page and its deploy
shape: Addendum 10.)

## 3. Annotation inventory

Commenting remains ONLY in the Plans reader — its full
Annotations-kit surface plus its foot AnchoredComment.
Everything else annotation-shaped is dropped:

- Overview's AnchoredComment
- the Inbox view and its nav entry
- the shell sent-count badge
- the Settings messages panel
- MessageComposer, if the kept Plans surface does not
  compose it (decided by grep over the kept surface)

Backend records and plans-used actions are untouched;
actions orphaned by a drop are flagged, not removed.
