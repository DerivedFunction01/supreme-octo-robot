#!/usr/bin/env python3
"""The local form's seal verbs for bin/venue-run: --seal
and --verify-sealed over the sealed register.

Split from the entry along the seal seam (the
local_attach precedent): the entry keeps thin bindings
that resolve the seams from its own globals at call time,
so a monkeypatched entry global is the binding this leaf
calls. Content is never printed by either verb — the
output names files and hashes only.
"""

import json


def seal_job(job_name: str, evidence: str | None, seams: dict) -> int:
    """Seal one job's script files in place: every file
    beside the manifest except job.json and existing
    blobs is encrypted to <name>.sealed under the
    runner's server-side key, its plaintext is deleted,
    and the register entry is written with each file's
    SHA-256 and the flag evidence."""
    fail = seams["fail"]
    sealed = seams["sealed"]
    repo = seams["repo"]
    manifest_path = seams["jobs_dir"] / job_name / "job.json"
    if not manifest_path.exists():
        return fail(f"no job manifest at {manifest_path}")
    if not evidence:
        return fail("--seal needs --evidence \"<the flag class and count that classes this job>\"")
    job_dir = manifest_path.parent
    candidates = sorted(
        p
        for p in job_dir.iterdir()
        if p.is_file() and p.name != "job.json" and not p.name.endswith(".sealed")
    )
    if not candidates:
        return fail(f"job {job_name}: no unsealed script files beside the manifest")
    key_path = sealed.ensure_key(repo)
    key = sealed.load_key(repo)
    files = []
    for path in candidates:
        data = path.read_bytes()
        files.append(
            {"name": path.name, "sha256": sealed.sha256_hex(data), "bytes": len(data)}
        )
        blob_path = path.with_name(path.name + ".sealed")
        sealed.staged_write(blob_path, sealed.seal_bytes(key, data))
        path.unlink()
    register = sealed.load_register(repo)
    entry = {
        "job": job_name,
        "sealed_at": seams["now"](),
        "evidence": evidence,
        "files": files,
    }
    register["jobs"] = [
        e for e in register.get("jobs", []) if e.get("job") != job_name
    ] + [entry]
    sealed.save_register(repo, register)
    print(
        json.dumps(
            {
                "job": job_name,
                "sealed": [f["name"] for f in files],
                "sha256": {f["name"]: f["sha256"] for f in files},
                "register": str(sealed.register_path(repo)),
                "key": str(key_path),
            },
            indent=2,
        )
    )
    return 0


def verify_sealed(job_name: str, seams: dict) -> int:
    """Open each of a sealed job's blobs in memory and
    compare against the register's hashes. Prints file
    names and match facts only — never content."""
    fail = seams["fail"]
    sealed = seams["sealed"]
    repo = seams["repo"]
    register = sealed.load_register(repo)
    entry = sealed.entry_for(register, job_name)
    if entry is None:
        return fail(f"job {job_name} is not in the sealed register")
    job_dir = seams["jobs_dir"] / job_name
    try:
        key = sealed.load_key(repo)
    except sealed.SealError as exc:
        return fail(str(exc))
    ok = True
    results = {}
    for f in entry["files"]:
        blob_path = job_dir / (f["name"] + ".sealed")
        if not blob_path.exists():
            results[f["name"]] = "blob missing"
            ok = False
            continue
        try:
            data = sealed.open_bytes(key, blob_path.read_bytes())
        except sealed.SealError as exc:
            results[f["name"]] = f"open failed: {exc}"
            ok = False
            continue
        match = sealed.sha256_hex(data) == f["sha256"]
        results[f["name"]] = "match" if match else "HASH MISMATCH"
        ok = ok and match
    print(json.dumps({"job": job_name, "files": results}, indent=2))
    return 0 if ok else 1
