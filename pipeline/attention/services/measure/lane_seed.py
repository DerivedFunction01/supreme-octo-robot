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
    termination condition. Venue is the session
    stem the declaration declares for every lane.
    A record path is carried relative to the
    workspace root — the greenfield-ci tree the
    lane homes live in — and the collector
    resolves it against the workspace anchor.
    """
    venue = "storm-mosaic-17"
    first = "2026-11-23T23:12:00-05:00"
    amended = "2026-11-24"
    register = (
        "Register delivered at greenfield-ci/"
        "{home}/register-*.md with a BUILD-READY or NOT verdict"
    )
    rows = [
        # key, label, minutes, declared_at, home, seat, condition
        (
            "segment-cure-continuation",
            "Segment cure continuation",
            120,
            first,
            "segment-formation",
            "successor",
            "Hand-back carrying branch tip SHA + gate verdict; "
            "packet lands at a named SHA",
        ),
        (
            "group-formation-probe",
            "Group-formation probe",
            240,
            first,
            "group-formation-probe",
            None,
            register.format(home="group-formation-probe"),
        ),
        (
            "decomposition-registry",
            "Decomposition portion registry.py",
            180,
            first,
            None,
            None,
            register.format(home="classify-decomposition"),
        ),
        (
            "decomposition-analysis",
            "Decomposition portion analysis.py",
            None,
            amended,
            None,
            None,
            register.format(home="classify-decomposition"),
        ),
        (
            "deferred-tax-s3-pricing",
            "Deferred_tax S3 pricing",
            180,
            first,
            "dt-s3-pricing",
            None,
            register.format(home="dt-s3-pricing"),
        ),
        (
            "inventory-d3-measurement",
            "Inventory D3 measurement",
            120,
            first,
            "inv-recall",
            "successor",
            register.format(home="inv-recall"),
        ),
    ]
    families = [
        ("income-statement", "Income statement", "is-residual"),
        ("fair-value", "Fair value", "fair-value-residual"),
        ("commitments", "Commitments/contingencies", "commitments-residual"),
        ("lease-maturity", "Lease maturity", "lease-residual"),
        ("debt-maturity", "Debt maturity", "debt-residual"),
        ("credit-losses", "Credit losses", "credit-losses-residual"),
        ("intangibles", "Intangibles", "intangibles-residual"),
        ("pension", "Pension", "pension-residual"),
        ("labor-contracts", "Labor contracts", "labor-residual"),
        ("restructuring", "Restructuring", "restructuring-residual"),
    ]
    for stem, label, home in families:
        rows.append(
            (
                f"{stem}-residual-pricing",
                f"{label} residual pricing",
                180,
                amended,
                home,
                None,
                register.format(home=home),
            )
        )
    rows += [
        (
            "firm-concentrated-trio",
            "Firm-concentrated trio adjudication",
            180,
            amended,
            "firm-concentrated",
            None,
            register.format(home="firm-concentrated"),
        ),
        (
            "segment-caption-pricing",
            "Segment caption pricing",
            180,
            amended,
            "segment-caption",
            "successor",
            register.format(home="segment-caption"),
        ),
        (
            "ci-gold-trace-pricing",
            "CI-gold trace pricing",
            60,
            amended,
            "ci-gold-trace",
            None,
            register.format(home="ci-gold-trace"),
        ),
        (
            "w-year-1-micro-cure",
            "W-YEAR-1 micro-cure",
            None,
            amended,
            None,
            None,
            "Closes at its landing",
        ),
    ]
    declarations = []
    for key, label, minutes, declared_at, home, seat, condition in rows:
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
