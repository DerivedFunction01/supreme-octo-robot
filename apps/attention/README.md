# apps/attention

The attention app: glance, Today, and Digest over the
evaluation and dispatch pipeline shapes — the decision
queue's presentation, nothing more.

- **Lands in:** its slot in step S8 alongside the other
  three apps (attention pin `7f13ae7`), after step S10's
  amendment work; stage deploy D5 (glance, Today, unified
  triage rows).
- **Governed by:** contract 09 (shell + the contractual
  presence asymmetry: the glance is presence-filtered, the
  decision queue never is), contract 05 (the send ledger
  and decision machinery it presents), contract 03 (the
  evaluator whose rows it renders), contract 06 (the
  vocabulary it renders, never re-derives). The product
  spec — row catalogue, queue semantics, Digest form —
  is `SPEC.md` beside this README.
- **Retains as its own:** the Today/Digest surfaces and the
  decision queue presentation. Verdicts, fulfillment,
  staffing rows, and push facts are pipeline derivations;
  Digest's workbench pull is a work-record pipeline feed —
  this app keeps no private workbench client (plan §9.4).
- The internal seams are cut along the review's call sites
  at integration (plan §9): evaluator, dispatch, work
  record, and fact measurement are pipeline services; this
  app is what remains on the surface side of those cuts.
