"""Lease unit tests: the pulse-stamp merge at save_record.

Pins the writer-side lost update: the reap
stamps last_pulse_at/last_pulse_result onto a fresh load on
its own cadence, but every other lease writer saves a whole
record from a copy loaded for its own mutation — a save
whose load straddled the reap's stamp overwrote the stamp
with stale values, so the records read pulse-stale for
hours while the reap reported pulse ok. save_record is the
one funnel: a fresher on-disk stamp is carried into the
saver's copy; the saver's own stamp, when fresher, wins.
"""

from datetime import timedelta

from unit_harness import NOW, lease, repo, seed_record  # noqa: F401

T_OLD = (NOW - timedelta(hours=3)).isoformat()
T_NEW = (NOW - timedelta(minutes=5)).isoformat()
T_NEWER = NOW.isoformat()


def _stamped(repo, at, result):
    rec = lease.load_record(repo)
    rec["last_pulse_at"] = at
    rec["last_pulse_result"] = result
    lease.save_record(repo, rec)
    return rec


def test_stale_saver_does_not_clobber_a_fresher_stamp(repo):
    seed_record(repo)
    _stamped(repo, T_OLD, "failed")
    # the reap stamps a fresh pulse onto its own fresh load
    _stamped(repo, T_NEW, "ok")
    # a writer whose copy predates the stamp saves its own
    # mutation (here: a jobs change in a stale copy)
    stale = lease.load_record(repo)
    stale["last_pulse_at"] = T_OLD
    stale["last_pulse_result"] = "failed"
    stale["caller"] = "workhorse"
    lease.save_record(repo, stale)
    on_disk = lease.load_record(repo)
    assert on_disk["last_pulse_at"] == T_NEW
    assert on_disk["last_pulse_result"] == "ok"
    # the saver's own mutation still landed
    assert on_disk["caller"] == "workhorse"
    # and the caller's dict carries the merged stamp too
    assert stale["last_pulse_at"] == T_NEW


def test_fresher_saver_stamp_wins(repo):
    seed_record(repo)
    _stamped(repo, T_NEW, "ok")
    _stamped(repo, T_NEWER, "failed")
    on_disk = lease.load_record(repo)
    assert on_disk["last_pulse_at"] == T_NEWER
    assert on_disk["last_pulse_result"] == "failed"


def test_first_save_and_unstamped_saves_stand(repo):
    seed_record(repo)
    rec = lease.load_record(repo)
    assert "last_pulse_at" not in rec
    lease.save_record(repo, rec)
    # a saver with no stamp does not invent one, and a disk
    # record with no stamp leaves the saver's fields alone
    rec["last_pulse_at"] = T_OLD
    rec["last_pulse_result"] = "failed"
    lease.save_record(repo, rec)
    on_disk = lease.load_record(repo)
    assert on_disk["last_pulse_at"] == T_OLD
    # an unstamped saver over a stamped record keeps the
    # stamp (disk is fresher than an absent stamp)
    bare = lease.load_record(repo)
    del bare["last_pulse_at"]
    del bare["last_pulse_result"]
    lease.save_record(repo, bare)
    on_disk = lease.load_record(repo)
    assert on_disk["last_pulse_at"] == T_OLD
    assert on_disk["last_pulse_result"] == "failed"
