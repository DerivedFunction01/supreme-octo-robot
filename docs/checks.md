# Checks

The composed gate is `check.py` at the repo root: its legs
read source. This file governs the legs that read the
built, served page instead.

### Rendered legs

The gate's legs read source; these legs read the built,
served page in a real browser. They run on a trigger — a
landing that touches a rendered surface, and on whatever
cadence the project sets for its census — through the
shard entry below, not inside `check.py`. The webapp
flavor seeds them: the specs and config under
`tests/e2e/`, the runner at `tools/e2e-shard.mjs`. Every
leg carries a synthetic capability test in its own file —
a page seeded with the leg's defect class must come back
flagged, a clean page empty — and runs it as part of the
family: a ruler that has never been seen red is not a
guard, and a leg that cannot produce its measurement has
not run.

- **Entry.** `node tools/e2e-shard.mjs <family>` is the
  one committed invocation. It checks its partition first
  (every spec file on disk claimed by exactly one family;
  an unassigned, double-assigned, or missing file fails
  before anything runs), gives each shard its own port and
  scratch directory, ensures the browser binary, and
  requires the port free before the run and again after it
  — a port still bound at the end is a teardown failure.
  With `--sha`, HEAD and the tracked tree must match the
  named commit before a leg measures anything: a verdict
  names the tree it was measured on. Families: `qa` (the
  legs below) and `app` (the project's own surface specs).
  Prerequisites the shard does not own: `npm install` at
  the repo root (the legs' toolchain, declared in the root
  `package.json`) and the client build (`bun run
  build:client` in `artifact/`).
- **The census.** `tests/e2e/surface-routes.ts` enrolls
  every user-facing route — its pattern, the concrete
  seeded path the legs drive, whether it renders, and the
  navigation landmarks it carries. The legs iterate the
  census and nothing else. A route joins when it is built,
  not after it breaks; a route that cannot yet pass is
  enrolled with its measured failure recorded beside it,
  and the record carries the defect without excusing it.
- **The serve route.** The suite serves the built client
  itself (`tests/e2e/serve.mjs`, started by
  `playwright.config.ts`): the built document statically,
  and the action transport answered from the serve's
  in-memory seeded state. The two reads the shell's own
  Settings sections consume outside any error boundary
  (getGlance, getDigest) answer the real backend's
  empty-state shapes; the two writes those sections post
  (postPresence, postDigestPrefs) land in the seeded
  state and are served back, so a control's effect is
  measured against the state the real path would paint;
  every other action answers a canned success envelope
  carrying an empty payload. No leg touches a deployed
  or live server, and no leg fires a real write at a live
  backend: a verdict over this serve route prices the
  rendered chrome and the surfaces as the seeded state
  serves them, and carries that boundary wherever it is
  cited.
- **Dead-click sweep** (`qa-dead-click.spec.ts`) — every
  visible, enabled control in each route's declared
  landmarks is clicked for real, and a click counts only
  on an observable effect: a navigation, a hash change, a
  dialog opening or closing, the control's own state
  flipping, a popup, or its landmark closing. Controls are
  re-found by identity, never by collection position.
  Mutating or session controls are skipped with the reason
  in the verdict — the sweep never mutates state to prove a
  control alive — and scheme links and self-links are
  verified by their href contract instead of a click, as
  current-state controls (an aria-current nav row, a
  selected radio) are by their state contract: the state
  a click would set already holds. This
  is the rendered complement of the misclick audit: the
  audit inventories committing controls, the sweep proves
  the chrome's controls answer. **Seeded** (S-4, 2026-11-18)
  — the family's one leg today.
- **Unseeded legs.** The axe leg (`qa-axe.spec.ts`), the
  geometry leg (`qa-geometry.spec.ts`), the truncation
  ruler (`qa-truncation.spec.ts`), and the parity leg
  (`qa-parity.spec.ts` over `tests/e2e/parity-views.ts`)
  are specified by the starter's checks text and are NOT
  seeded in this repo: no spec file, no partition claim.
  A leg the project has not seeded is unexercised, never
  passed; each joins by the change that seeds its spec and
  its partition claim together, as the dead-click sweep
  did.
- **Findings become pins.** A rendered defect confirmed by
  a critic run or by use becomes a spec in the `qa` family
  pinning the behaviour, landing with the fix where the fix
  is the project's — the family grows from findings, so a
  class caught once is caught by the gate thereafter. For
  a project on the generic UI kit, the kit's Specimen is
  the first surface enrolled: it joins the census and,
  once its render is approved, the parity manifest.
