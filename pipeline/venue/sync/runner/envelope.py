"""The grouped launch envelope's budget arithmetic: pure
functions over declared venue capacity, homed in a leaf so
the dispatch entry and the tests reach it without the
runner's foundation (the manifest_shape placement rule).

An envelope coalesces N jobs pending on one venue into ONE
launch with one thread budget for the whole envelope,
divided among the grouped jobs — instead of N independent
trees each spawning uncapped pools against the venue's pid
ceiling (the mergegate4 starvation class: one test worker
burst to ~710 threads and held the ceiling). The jobs run
concurrently inside the envelope, each at its divided
share; grouping never serializes.

The division's binding term is the WORKER COUNT, priced
against a declared worst case. Live evidence (the
mergegate4 fire) shows the bursting thread pool does NOT
honour the stamped pool caps — its environment carried
pool caps of 2 and a worker still burst to ~710 threads —
so the pool-cap stamps (OMP_THREAD_LIMIT and siblings) are
ADVISORY: they bind the libraries that honour them, and the
worker count is the cap that binds the rest. Each job's
worker count is therefore priced so that even if every
worker bursts to the declared worst case, the job stays
inside its thread share:

    workers = max(1, min(cores // n_jobs,
                         thread_share // per_worker_worst_case))

Two pool classes stand behind that pricing (the thread
census's finding):

- The connection pool (the DuckDB class): a per-connection
  thread pool — measured +39 threads per connection at 8
  cores — that honours NO env cap (the thread delta is
  identical capped and uncapped). It is priced by workers
  × connections only. A job that holds connections declares
  them per job in the envelope (connections,
  threads_per_connection); its per-worker worst case is
  connections × threads_per_connection + 150 of
  controller/subprocess overhead, replacing the flat burst
  figure for that job.
- The import pool (the numeric-stack class): the pools the
  stamped env caps (OMP_THREAD_LIMIT and siblings) do bind.

burst_per_worker defaults to 860 — the mergegate evidence's
~710-thread burst plus ~150 of controller/subprocess
overhead — and an envelope declaration may override it.
The observed plateau under that worst case: mergegate5's
sampler read 550 threads at 1 worker for a large suite,
inside the 860 the division prices. With the default, a
thread share of 384 prices workers = 1: the same form the
coordinator hand-set for the first envelope consumer after
the burst. A solo job's envelope (n_jobs = 1) divides the
full budget to that one job.

divide() splits the budget as thread_share = budget //
n_jobs per job, with the division remainder going one each
to the FIRST jobs in order (stated here because the record
carries the constituents in order and the shares must be
reproducible from it). pool_cap = max(1, thread_share //
workers): the advisory per-worker pool cap stamped beside
the worker count.

The budget is priced net of the system reserve
(SYSTEM_RESERVE_THREADS): the venue's own system set —
the sampler, the actuator, the trim, sshd and the runner's
own sessions — holds that many table slots outside every
programme budget, so the machinery that cures a saturation
can always fork inside one. The reserve comes off the
ceiling before the fraction is taken, and the classifier's
saturation line carries the same floor (venue_classify):
programme work is refused while the table's free remainder
is inside the reserve, whatever the configured ratio says.
"""

import re

_NAME_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

DECLARED_CAPACITY = {
    "local": {"cores": 16, "pids": 1024},
    "local-hp": {"cores": 8, "pids": 1024},
}

DEFAULT_FRACTION = 0.75
SYSTEM_RESERVE_THREADS = 128
DEFAULT_BURST_PER_WORKER = 860
WORKER_OVERHEAD_THREADS = 150

POOL_CAP_STAMPS = (
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def declared_capacity(shape_id):
    """The declared capacity for a shape id, or None when
    the shape declares none — an envelope over an
    undeclared shape refuses rather than inventing one."""
    capacity = DECLARED_CAPACITY.get(shape_id)
    return dict(capacity) if capacity is not None else None


def envelope_budget(pids_capacity: int, fraction: float = DEFAULT_FRACTION) -> int:
    """The envelope's total thread budget: the named
    fraction of the venue's pid ceiling net of the system
    reserve, floored — the reserve is never budgeted to
    programme work, at any fraction."""
    return int(max(0, pids_capacity - SYSTEM_RESERVE_THREADS) * fraction)


def connection_worst_case(connections: int, threads_per_connection: int) -> int:
    """A connection-pool job's per-worker worst case:
    connections × threads_per_connection, plus the standing
    controller/subprocess overhead."""
    return connections * threads_per_connection + WORKER_OVERHEAD_THREADS


def declared_worst_case(entry) -> "int | None":
    """The per-worker worst case a job entry declares, or
    None when it declares no connection pool (the envelope's
    burst_per_worker governs it then). A job entry is a
    plain name, or a mapping {name, connections,
    threads_per_connection}."""
    if not isinstance(entry, dict):
        return None
    connections = entry.get("connections")
    per = entry.get("threads_per_connection")
    if connections is None and per is None:
        return None
    return connection_worst_case(connections, per)


def divide(
    budget: int,
    cores: int,
    n_jobs: int,
    burst_per_worker: int = DEFAULT_BURST_PER_WORKER,
    worst_cases=None,
) -> list:
    """Divide one envelope budget among n_jobs grouped jobs,
    in order. Returns one dict per job:
    {workers, thread_share, pool_cap} — the stamps the
    launch environment carries. The remainder of the budget
    division goes one each to the first jobs in order.
    workers is the binding cap (see the module docstring):
    the job's core share bounded by what its thread share
    affords at its per-worker worst case — worst_cases[j]
    when the job declares one, else burst_per_worker —
    floored at 1 so a grouped job always runs."""
    base = budget // n_jobs
    remainder = budget % n_jobs
    core_share = cores // n_jobs
    divisions = []
    for index in range(n_jobs):
        thread_share = base + (1 if index < remainder else 0)
        worst = burst_per_worker
        if worst_cases is not None and worst_cases[index] is not None:
            worst = worst_cases[index]
        workers = max(1, min(core_share, thread_share // worst))
        pool_cap = max(1, thread_share // workers)
        divisions.append(
            {
                "workers": workers,
                "thread_share": thread_share,
                "pool_cap": pool_cap,
            }
        )
    return divisions


def entry_name(entry) -> "str | None":
    """A job entry's name: the entry itself when it is a
    plain name, its "name" field when it is a mapping."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        name = entry.get("name")
        return name if isinstance(name, str) else None
    return None


def envelope_error(spec) -> "str | None":
    """A loud-refusal verdict for an envelope declaration
    (adapters/local/jobs/<name>/envelope.json): {shape,
    jobs: [job entries in order], fraction?,
    burst_per_worker?, caller?, timeout_s?}. A job entry is
    a plain job name, or a mapping {name, connections,
    threads_per_connection} declaring the job's connection
    pool. Returns an error naming the field, or None when
    the declaration is the contract's. Job and envelope
    names become venue paths, so the name shape is the
    run-id-safe one."""
    if not isinstance(spec, dict):
        return f"envelope declaration must be a mapping, got {type(spec).__name__}"
    shape = spec.get("shape")
    if not isinstance(shape, str) or not shape:
        return "envelope shape must name a shape id"
    if shape not in DECLARED_CAPACITY:
        return f"envelope shape {shape!r} declares no capacity — the envelope prices from declared capacity only"
    jobs = spec.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return "envelope jobs must be a non-empty list of job entries"
    seen = set()
    for entry in jobs:
        name = entry_name(entry)
        if name is None or not name:
            return f"envelope job entry does not name a job: {entry!r}"
        if not _NAME_SAFE.match(name):
            return f"envelope job {name!r} is not a path-safe job name"
        if name in seen:
            return f"envelope job {name!r} is named twice — a job runs once inside its envelope"
        seen.add(name)
        if isinstance(entry, dict):
            connections = entry.get("connections")
            per = entry.get("threads_per_connection")
            if (connections is None) != (per is None):
                return f"envelope job {name!r}: connections and threads_per_connection are declared as a pair"
            if connections is not None:
                for field, value in (
                    ("connections", connections),
                    ("threads_per_connection", per),
                ):
                    if (
                        not isinstance(value, int)
                        or isinstance(value, bool)
                        or value < 1
                    ):
                        return f"envelope job {name!r}: {field} must be a positive integer, got {value!r}"
    fraction = spec.get("fraction", DEFAULT_FRACTION)
    if (
        not isinstance(fraction, (int, float))
        or isinstance(fraction, bool)
        or not 0 < fraction <= 1
    ):
        return f"envelope fraction must be a number in (0, 1], got {fraction!r}"
    burst = spec.get("burst_per_worker", DEFAULT_BURST_PER_WORKER)
    if not isinstance(burst, int) or isinstance(burst, bool) or burst < 1:
        return f"envelope burst_per_worker must be a positive integer, got {burst!r}"
    caller = spec.get("caller")
    if caller is not None and not isinstance(caller, str):
        return f"envelope caller must be a string, got {caller!r}"
    timeout = spec.get("timeout_s")
    if timeout is not None and (
        not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1
    ):
        return f"envelope timeout_s must be a positive integer, got {timeout!r}"
    return None
