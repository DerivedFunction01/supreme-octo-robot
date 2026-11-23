# apps/workbench

The workbench app: the viewer sections and components over
work-record served shapes — home, entries, plans, todos,
board, inbox, overview, settings, and the per-project Code
section (git as a facet of the project; the Repos
destination retired, SPEC §21).

- **Lands in:** step S8 (workbench pin `b0b9cc5`), stage
  deploy D3, on the extracted Workhorse Kit v1 (S2) and the
  one shell. Backend half: the served-shape adapters over
  the work-record pipeline (`pipeline/workrecord`,
  `pipeline/evaluation`).
- **Governed by:** contract 09 (app shell), contract 11
  (the records and feeds it renders), contract 06 (status
  presentation — the kit's table).
- **Retains as its own:** todo/plan/bundle records and the
  board surfaces. The app owns the todo record; the
  pipeline owns the arm/retire act over it (contract 03).
- The old message Inbox surface does not carry over as a
  second dispatch — the messages/outbox mechanism retires
  into the one substrate (contract 05).
