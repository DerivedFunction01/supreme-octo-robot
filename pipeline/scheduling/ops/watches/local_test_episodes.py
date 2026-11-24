#!/usr/bin/env python3
"""First-sighting handling for the local-test watch.

One new episode's reporting lives here: the explained line
(a reappearing signature with a closed disposition), the
ops-route line (the ledger consult in local_test_ledger.py
covers the sampled process — a scheduler-server child, not a
local run — so no defect item and no sends), and the defect
path (attention item, main copy, routed copy, disposition
entry, warning line). Extracted from local_test_watch.py's
run() along its real seam — the watch owns sampling,
classification, and episode bookkeeping; this module owns
what a first sighting says.

The ledger consult is fail-safe: an unreadable ledger or an
uncovered finding falls through to the defect path exactly
as before.
"""


def handle_first_sighting(ctx):
    """Returns (line, disp_dirty): the cycle line for this
    sighting (always exactly one) and whether the caller must
    persist the disposition record."""
    finding = ctx["finding"]
    sig = ctx["sig"]
    at = ctx["at"]
    defects = ctx["defects"]
    argv_text = " ".join(finding["argv"])
    derived_mark = " cwd-derived=argv" if finding.get("derived") else ""
    label = ctx["label"]
    if defects.is_explained(ctx["dispositions"], sig):
        # The same explained process, on the record:
        # no defect item, no sends — one line per
        # episode names the standing disposition.
        return (
            "LOCAL-EXEC EXPLAINED kind=%s runner=%s cwd=%s%s "
            "argv=%s load=%s sessions_live=%d thread=%s "
            "sig=%s disposition=closed-legitimate-tooling "
            "first-seen=%s"
            % (finding.get("kind", "test"), finding["runner"],
               finding["cwd"], derived_mark, argv_text, ctx["load"],
               ctx["live_count"], label, sig, at)), False
    citation = ctx["ledger_lookup"](finding, at)
    if citation is not None:
        # Covered by a scheduler op whose target runs the
        # automation surface (the consult's surface test is
        # the discriminator): recorded here, never warned.
        # An ad-hoc sched-exec command never reaches this
        # branch — it takes the defect path below.
        return (
            "LOCAL-EXEC OPS-ROUTE kind=%s runner=%s cwd=%s%s "
            "argv=%s load=%s sessions_live=%d thread=%s "
            "sig=%s op=%s caller=%s first-seen=%s"
            % (finding.get("kind", "test"), finding["runner"],
               finding["cwd"], derived_mark, argv_text, ctx["load"],
               ctx["live_count"], label, sig, citation["op_id"],
               citation["caller"], at)), False
    # The defect item: one per episode, deduped at the
    # surface by handle + source_ref.
    item_poster = ctx["item_poster"]
    if item_poster is None:
        item_outcome = "unconfigured"
    else:
        try:
            payload = defects.build_item_payload(
                sig, finding, ctx["programme"], label, ctx["mode"],
                ctx["live_count"], ctx["load"], at)
            item_outcome = "posted" if item_poster(payload, at) \
                else "failed"
        except Exception:
            item_outcome = "failed"
    # The main copy: the routes file's `main` key is
    # the destination; absent route or sender, the
    # outcome on the line is print-only.
    routes = ctx["routes"]
    sender = ctx["sender"]
    main_route = routes.get("main") or None
    main_outcome = "print-only"
    if main_route and sender is not None:
        main_outcome = defects.send_outcome(
            sender, main_route["chat_id"],
            "LOCAL-EXEC WARNING (local-test-watch, first "
            "sighting): %s execution on the local box, "
            "programme %s (%s). cwd=%s argv=%s load=%s "
            "mode=%s sessions_live=%d. Defect item %s "
            "raised on the attention surface; disposition "
            "sig=%s." % (
                finding.get("kind", "test"), ctx["programme"], label,
                finding["cwd"], argv_text, ctx["load"], ctx["mode"],
                ctx["live_count"], defects.item_id(sig), sig),
            "local-test-watch-main-" + sig)
    routed = "print-only"
    if ctx["strict"] and ctx["route"] and sender is not None:
        text = (
            "LOCAL-EXEC WARNING (local-test-watch, first "
            "sighting): %s execution on the local box while "
            "%d High-RAM session(s) are live. cwd=%s argv=%s "
            "load=%s. Venue rule: no checks or code run "
            "locally while the fleet is up — re-route to a "
            "High-RAM session." % (
                finding["kind"], ctx["live_count"],
                finding["cwd"], argv_text, ctx["load"]))
        routed = defects.send_outcome(sender, ctx["route"]["chat_id"], text,
                       "local-test-watch-" + sig)
    outcomes = {"thread": routed, "main": main_outcome,
                "item": item_outcome}
    defects.open_entry(
        ctx["dispositions"], sig, finding, ctx["programme"], at, outcomes)
    if not ctx["strict"]:
        return (
            "LOCAL-TEST %s cwd=%s%s argv=%s load=%s sig=%s "
            "thread=%s main=%s item=%s first-seen=%s"
            % (finding["runner"], finding["cwd"], derived_mark,
               argv_text, ctx["load"], sig, label, main_outcome,
               item_outcome, at)), True
    return (
        "LOCAL-EXEC WARNING kind=%s runner=%s cwd=%s%s argv=%s "
        "load=%s sessions_live=%d thread=%s routed=%s "
        "sig=%s main=%s item=%s first-seen=%s"
        % (finding["kind"], finding["runner"], finding["cwd"],
           derived_mark, argv_text, ctx["load"], ctx["live_count"],
           label, routed, sig, main_outcome, item_outcome, at)), True
