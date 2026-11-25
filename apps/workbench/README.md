# apps/workbench

The workbench app: the viewer sections and components over
work-record served shapes — home, overview, goals, mockups,
entries, plans, todos, board, inbox, task manager, settings,
and the per-project Code section (git as a facet of the
project; the Repos destination is retired, work-record SPEC
§21). Its frontend is `frontend/` (package
`workbench-frontend`).

- **Backend:** the served-shape adapters over the
  work-record pipeline (`pipeline/workrecord`,
  `pipeline/evaluation`).
- **Governed by:** contract 09 (app shell), contract 11
  (the records and feeds it renders), contract 06 (status
  presentation — the kit's table).
- **Retains as its own:** todo/plan/bundle records and the
  board surfaces. The app owns the todo record; the
  pipeline owns the arm/retire act over it (contract 03).
- The old message Inbox surface does not carry over as a
  second dispatch — the messages/outbox mechanism retires
  into the one substrate (contract 05). The Inbox section
  that remains is a viewer section over served feeds, not
  a dispatch path.
