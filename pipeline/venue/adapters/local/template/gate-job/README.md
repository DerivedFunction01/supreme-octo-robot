# Gate-job template — the canonical venue-job wrap

The finished form of the gate/formation wrap every lane gate
fire forms from: seed formation, hermetic per-run DEST, tree
assertion by sha, scoped `check.py` invocation, product
emission. It generalizes the wraps lane jobs previously
copied from each other per fire (the divergence cost record:
the probe-retirement gate ledger, fires 4–5 — a shared-DEST
franken-tree and a co-tenant rebuild race, both cured by the
hermetic job-private form this template canonizes).

## Formation

1. Copy `run.sh.template` to `jobs/<job-name>/run.sh` and
   `job.json.template` to `jobs/<job-name>/job.json`.
2. Substitute the tokens in both files:
   - `__JOB_NAME__`, `__CALLER__` — the job's name and its
     registered caller.
   - `__BRANCH__`, `__WANT_SHA__` — the clone source branch
     and the full sha of the tree the gate judges.
   - `__ASSERT_TIP__` — `1` for a transport-branch gate (the
     branch tip must equal the gated sha; the wrap verifies
     by ls-remote before cloning); `0` for a landed tree (an
     ancestor sha; the HEAD assertion alone binds).
   - `__CHECK_PATHS__` — the scoped check targets for the
     delta under gate, never `--all`.
   - `__WORKERS__`, `__THREADS__` — sized from the venue's
     resource probe (cgroup cpu/memory) at formation; never
     constants copied from another machine.
3. Plant the clone source: write the gated repo's clone URL
   (resolved from the repos registry) into `repo-url.txt`
   beside `run.sh`, and name it in the manifest's `uploads`
   (the `__REPO_URL_PLANT__` token) so it ships beside the
   script into the run dir; or pass `REPO_URL` in the job
   environment. The URL is provisioned material — it never
   enters a tracked file; `repo-url.txt.example` is the
   tracked form.
4. Populate the composition expectations in `run.sh` from
   the gated head: `EXPECTED_SHA256` with the sha256 of each
   delta file's content at the head, `EXPECTED_ABSENT` with
   each path the delta removes (or a path whose absence the
   gate must guarantee). In a clone formation the HEAD sha
   already binds the whole tree; the per-file entries are
   the assertion of record for the delta's own files, read
   before any verdict.
5. Fire through the runner (`bin/venue-run <job-name>
   --caller <caller>`) and read the verdict from the run's
   `products/gate-result.json`.

## The wrap's discipline

- Hermetic DEST: the tree forms at `work/tree` inside the
  job's own run dir, rebuilt from the clone alone. A shared
  checkout is never a gate's formation path.
- Assertion before verdict: branch tip (in the
  transport-branch form), HEAD == gated sha, every expected
  file's sha256, every expected absence — all verified and
  recorded (`state: composed`, `composition: exact`) before
  the check runs. A mismatch fails the wrap; no verdict is
  read from a mis-composed tree.
- Scoped check, once: `check.py <paths> --workers <n>` over
  the delta's affected paths. On red, one re-proof in the
  same fire; both runs stand in the products (`check.txt`,
  `check-reproof.txt`) and the re-proof is the verdict
  source when it fires.
- Products: `gate-result.json` (job, state, want/head,
  composition, assertion counts, check_rc, verdict_source,
  test counts), `check.txt`, `check-reproof.txt` when
  fired, `venv-log.txt`, `gate-log.txt`. The wrap exits
  with the check's rc, so the run record's exit code
  carries the verdict.

## Seeded/delta formation

Where a tree cannot ride a branch (a genuinely uncommitted
tree), the same wrap forms from a seed plus a delta instead
of a clone: the seed (base tree + its venv, formed by the
tree's own `init_venv.py` when absent, preserved across the
rebuild when present) is extracted hermetically at DEST,
the delta and its deletions manifest are applied, and the
same assertion block verifies composition — per-file sha256
against the head's contents, deletions counted and absent —
before the identical check and emission stages. The wrap of
record for that form is the probe-retirement gate wrap
(fire 9: composition exact, check rc 0).
