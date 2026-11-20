# apps/runner

The runner app: the lease panel over the venue layer's
served portions — leases, budget, grant, orphans, events —
rendering the fleet as one fleet with the venue named on
every record.

- **Lands in:** step S8 (runner pin `636033b`) over the S5
  venue pipeline; stage deploy D4 (venue-keyed leases,
  budget, events).
- **Governed by:** contract 09 (app shell); the portions
  themselves are the venue layer's served shapes
  (`pipeline/venue`) — the panel renders only served state
  and derives nothing, the cleanest pipeline/app split of
  the four at the pin.
- **Retains as its own:** the lease panel surfaces. Panel
  starts carry `acquire --create` (creations, never
  adoptions) — the operator ruling the core enforces.
- Anything the panel shows that cannot name its venue is a
  defect (D2 binding rule, plan §7 V4).
