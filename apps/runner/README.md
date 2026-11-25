# apps/runner

The runner app: the lease panel over the venue layer's
served portions — leases, budget, grant, orphans, events —
rendering the fleet as one fleet with the venue named on
every record. Its frontend is `frontend/` (package
`runner-frontend`).

- **Governed by:** contract 09 (app shell); the portions
  themselves are the venue layer's served shapes
  (`pipeline/venue`) — the panel renders only served state
  and derives nothing.
- **Retains as its own:** the lease panel surfaces. Panel
  starts carry `acquire --create` (creations, never
  adoptions) — the operator ruling the venue core enforces
  (`pipeline/venue/ui/route_surface.py`).
- Anything the panel shows that cannot name its venue is a
  defect.
