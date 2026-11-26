# apps/attention

The attention app: the glance, Today, and Digest surfaces
over the evaluation and dispatch pipeline shapes — the
decision queue's presentation, nothing more. Its surfaces
live in the one integrated frontend (artifact/client, the
attention views); the standalone frontend this app once
carried is dropped and does not exist.

- **Governed by:** contract 09 (shell + the contractual
  presence asymmetry: the glance is presence-filtered, the
  decision queue never is), contract 05 (the send ledger
  and decision machinery it presents), contract 03 (the
  evaluator whose rows it renders), contract 06 (the
  vocabulary it renders, never re-derives). The product
  spec — row catalogue, queue semantics, Digest form —
  is `SPEC.md` beside this README.
- **Retains as its own:** the glance, Today, and Digest
  surfaces and the decision queue presentation. Verdicts,
  fulfillment, staffing rows, and push facts are pipeline
  derivations (`pipeline/attention`, `pipeline/evaluation`,
  `pipeline/dispatch`); Digest's workbench pull is a
  work-record pipeline feed — this app keeps no private
  workbench client.
- Evaluator, dispatch, work record, and fact measurement
  are pipeline services; this app is what remains on the
  surface side of those cuts.
