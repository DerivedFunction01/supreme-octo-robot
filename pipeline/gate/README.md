# Pipeline gate

## Purpose

The one home for the gate legs the four workhorses used to
copy per repo (plan §4.16, canonical owner: the pipeline
gate). The repo-root `check.py` composes each package's
declared legs into its gate; §6 P1's runner service will
execute this gate and record verdicts against tree SHAs —
it does not invoke per-repo check files.

## Contracts

- **Components, one implementation each.** `linecap.py`
  (the line cap, repo-scoped: 800 lines,
  a file at the cap passes; a 700-line creep band lists
  non-test files on every run and bans growth past the
  file's committed count at HEAD; the root check runs it
  once over every tracked code file in the tree — coverage
  is by default, declared nowhere; the scheduler's
  `git ls-files` enumeration survives in its package form),
  `portability.py` (the
  portability/denylist scanner, lifted from the scheduler;
  fed by one untracked denylist per deployment),
  `staticlegs.py` (ruff format/lint and the policy-scanner
  leg), `isolation.py` (the test-isolation state hash),
  `foldercensus.py` (the folder census: tracked files per
  folder over the tracked-only enumeration; warn 16 / fail
  24 in the composed gate's config; single-kind family
  folders are exempt by gate.json declaration and always
  reported),
  `targeting/` (the AST test-targeting mechanism ported
  from programme-a's check.py lineage: snapshot, prose-only
  exclusion, reverse import lineage, explainable reasons),
  `venvbuild.py` (one `find_uv`, one venv builder,
  parameterized by per-package config). Three more
  components run repo-scoped by default since the
  default-on reversal, in the line cap's form — the root
  check executes each once per run, their recorded
  exceptions ride this package's repo leg declarations as
  data, and no package declares coverage:
  `writeruniqueness.py` over every tracked Python source
  in the tree (the repowriteruniqueness row),
  `importisolation.py` for every composed pipeline
  package automatically (the repoimportisolation row),
  and the scanner-runner contract (`staticlegs.scanners`)
  over every package carrying a `scanners.py` module,
  discovered from the tree (the reposcanners row).
- **Declarations are data.** Each package names its legs
  in a `gate.json` beside its code; the app frontends'
  legs are served-by declarations in `frontends.json`
  (served by the app suites and the kit — declared, never
  re-implemented here). A package's own legs (scheduling's
  validate/census) ride as command data in its declaration.
- **Fail-fast in declared order** within a package — the
  retired check files' semantics. A leg filter
  (`check.py --legs`) is diagnostic and runs every
  selected leg.
- **Verdict parity is the standing proof burden** for any
  change to a component: the composed gate reproduces
  each package's own gate verdict on the same tree.

## Deliberate gaps

- Attention's `check.py` legs over the tree that moved
  at S7 (`pipeline/registry`, the migrated attention
  store's home) landed as declarations at S10: the
  portability component leg and the
  suite in its isolation-wrapped form over the live
  state home (`var/`). Two of the original legs remain
  open as named findings, not exemptions: the ruff
  format/lint legs (no interpreter in the deployment
  carries ruff, so a declaration would run red on every
  tree) and the scanner-runner leg (attention's scanner
  suite was never ported into this tree; its surviving
  substance is the linecap/portability/pathdiscipline
  components themselves).
- The runner's `colab-check` venue funnel (§7) becomes a
  declaration when S5 closes; the venue tree carries no
  gate.json in this step.
- The lineage graph is rebuilt in memory per run (under a
  second at this repo's scale); the source mechanism's
  on-disk cache is not carried.
