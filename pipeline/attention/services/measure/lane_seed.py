"""Seeded lane declarations (lane-records plan): the
coordinator declarations transcribed into the
registry-contract form, one builder per programme
that seeds lanes. The registry carries the built
entries on its programme row; they amend by commit
with the contract, as the staffable queue does. A
lane's own record blocks, once they land in a
declared record file, supersede its seed entry by
key at collection time.
"""


def edgar_lane_declarations() -> list[dict]:
    """The edgar coordinator's standing lane
    declaration, transcribed from its durable
    record: key, label, estimate minutes (None
    where the declaration states none), declared-at
    (its stated datetime, else its stated date),
    the lane home its termination path names (its
    STATE file is the lane's record), its seat
    where the declaration names one, and its
    termination condition. Venue is per lane: the
    fleet member the declaration names for that
    lane's work, or "none" where the lane fires no
    venue work. A record path is carried relative
    to the workspace root — the greenfield-ci tree
    the lane homes live in — and the collector
    resolves it against the workspace anchor.

    Current transcription: coordinator successor
    III's declaration as posted at the owner's
    thread close-out, 2026-11-25 — eleven lanes in
    flight (ten family lanes, one formation lane).
    The lanes closed at that close-out (21 family
    lanes archived on bar or on exhaustion-grade
    proven-NOT, and the spent union v3 formation
    lane) are not carried forward.
    """
    declared = "2026-11-25"
    register = (
        "Register delivered at greenfield-ci/"
        "{home}/register-*.md with a BUILD-READY or NOT verdict"
    )
    # key, label, venue, home — family lanes in
    # flight. Venue is the fleet member the
    # declaration names; load-routed lanes carry
    # the member their recent work rode.
    families = [
        ("restructuring", "Restructuring", "local-main", "restructuring"),
        ("equity-statement", "Equity statement", "local-main", "equity-statement"),
        ("pension", "Pension", "local-main", "pension"),
        (
            "stock-comp-rollforward",
            "Stock comp rollforward",
            "local-hp",
            "stock-comp-rollforward",
        ),
        ("cash-flow", "Cash flow", "local-main", "cash-flow"),
        (
            "goodwill-rollforward",
            "Goodwill rollforward",
            "local-hp",
            "goodwill-rollforward",
        ),
        (
            "shares-purchased",
            "Shares purchased",
            "local-main",
            "shares-purchased",
        ),
        ("inventory", "Inventory", "local-main", "inventory"),
        ("debt-maturity", "Debt maturity", "none", "debt-maturity"),
        ("lease-maturity", "Lease maturity", "none", "lease-maturity"),
    ]
    rows = [
        (
            key,
            label,
            None,
            declared,
            home,
            None,
            register.format(home=home),
            venue,
        )
        for key, label, venue, home in families
    ]
    rows.append(
        (
            "packet-union-formation",
            "Packet union formation",
            None,
            declared,
            None,
            "coordinator",
            "Hand-back carrying branch tip SHA + gate verdict; "
            "packet lands at a named SHA",
            "local-main",
        )
    )
    declarations = []
    for key, label, minutes, declared_at, home, seat, condition, venue in rows:
        entry = {
            "key": key,
            "label": label,
            "venue": venue,
            "estimate_minutes": minutes,
            "declared_at": declared_at,
            "record": f"greenfield-ci/{home}/STATE.md" if home else None,
            "termination_condition": condition,
        }
        if seat:
            entry["seat"] = seat
        declarations.append(entry)
    return declarations
