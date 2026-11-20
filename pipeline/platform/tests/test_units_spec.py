"""The unit render set's coverage (the survival build,
2026-11-15): ops/units-spec.json is the render set of
record for install-units.sh, and it must cover every
unit template the platform carries — a template with no
spec entry is a unit nothing re-renders after a VM
replacement, which is the defect the survival build
closes. The spec's value seams must also match each
template's tokens exactly: a seam the template does not
carry is dead weight, and a token with no seam fails
the render at install time, on the ladder's cadence,
instead of here.

The set's shape (extended by the watchdog actuation
cure, 2026-11-15): the three fleet services, and per
fleet unit a watchdog driver pair — a oneshot ladder
service (enable:false; its timer is the enablement)
and the timer that starts it. A timer entry's unit key
is its installed stem plus "-timer" (the installed
name itself is the service's name with .timer), so
every key stays unique while the pairing stays
readable from the spec alone.
"""

import json
import re
import unittest
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parents[1] / "ops"
TOKEN_RE = re.compile(r"@([A-Z_]+)@")


def _spec():
    with open(OPS_DIR / "units-spec.json",
              encoding="utf-8") as fh:
        return json.load(fh)


FLEET_UNITS = ("workhorse", "workbench", "venue")


class RenderSetCoverageTests(unittest.TestCase):
    def test_every_template_has_a_spec_entry(self):
        templates = {path.name
                     for path in OPS_DIR.glob("*.tmpl")}
        entries = {entry["template"] for entry in _spec()}
        self.assertEqual(entries, templates)

    def test_entries_name_their_template_and_unit(self):
        for entry in _spec():
            self.assertTrue(
                (OPS_DIR / entry["template"]).is_file(),
                entry["template"])
            self.assertEqual(
                entry["out"] + ".tmpl", entry["template"])
            if entry["out"].endswith(".timer"):
                # A timer's key is its installed stem
                # plus "-timer"; the installed name is
                # the paired service's name with .timer.
                self.assertEqual(
                    entry["unit"],
                    entry["out"][:-len(".timer")] + "-timer")
            else:
                self.assertEqual(
                    entry["out"], entry["unit"] + ".service")

    def test_watchdog_driver_pairs_cover_the_fleet(self):
        spec = {entry["unit"]: entry for entry in _spec()}
        for unit in FLEET_UNITS:
            service = spec[f"{unit}-watchdog"]
            timer = spec[f"{unit}-watchdog-timer"]
            # The ladder service is never enabled in its
            # own right (no [Install] in its template);
            # the timer carries the enablement.
            self.assertIs(service.get("enable"), False)
            self.assertNotIn("enable", timer)
            self.assertEqual(
                set(service["values"]), {"ROOT", "HOME"})
            self.assertEqual(timer["values"], [])
            timer_text = (
                OPS_DIR / timer["template"]).read_text(
                encoding="utf-8")
            self.assertIn(
                f"Unit={unit}-watchdog.service", timer_text)
            self.assertIn("OnUnitActiveSec=60", timer_text)
            service_text = (
                OPS_DIR / service["template"]).read_text(
                encoding="utf-8")
            self.assertIn(
                f"Environment=WORKHORSE_UNIT={unit}",
                service_text)
            self.assertIn("ops/watchdog.sh", service_text)

    def test_units_and_outputs_are_unique(self):
        spec = _spec()
        self.assertEqual(
            len({entry["unit"] for entry in spec}),
            len(spec))
        self.assertEqual(
            len({entry["out"] for entry in spec}),
            len(spec))

    def test_value_seams_match_template_tokens(self):
        for entry in _spec():
            text = (OPS_DIR / entry["template"]).read_text(
                encoding="utf-8")
            self.assertEqual(
                set(entry["values"]),
                set(TOKEN_RE.findall(text)),
                entry["template"])

    def test_the_installer_reads_the_spec(self):
        # The spec is the render set of record, not a
        # second table the installer keeps privately:
        # install-units.sh must name it.
        script = (OPS_DIR / "install-units.sh").read_text(
            encoding="utf-8")
        self.assertIn("units-spec.json", script)


if __name__ == "__main__":
    unittest.main()
