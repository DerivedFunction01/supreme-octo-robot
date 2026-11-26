#!/usr/bin/env python3
"""Portability scanner — loader re-point to the pipeline
gate component.

The implementation lives once, in the pipeline gate
package (pipeline/gate/portability.py; plan §4.10,
completed by §4.16), fed by one untracked denylist per
deployment. This file carries no scanning logic: it loads
the component's source into its own module namespace, so
this module keeps behaving exactly as the file that used
to live here — including the suite's pinned seam of
patching this module's EXCEPTION_FILES registry, which
only works when the functions' globals are this module's
own dict. Standalone, the scan root defaults to this
package's root, as the original's did.
"""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scheduling_paths",
    str(Path(__file__).resolve().parent.parent / "paths.py"))
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

_COMPONENT = Path(_paths.GATE_PORTABILITY)
# The component's import of its denylist_match sibling has
# two forms: the package-relative form (when the gate
# package itself is imported) and the bare form for
# standalone script use, which expects the component's own
# directory on sys.path — as running the component directly
# provides. This loader execs the source into its own
# namespace, where neither holds unless the directory is
# put on the path here; without it the load dies with
# ModuleNotFoundError (the defect the argv lane's flag
# named: this suite's scanner test erroring at load in the
# gate runner's own unittest context).
_COMPONENT_DIR = str(_COMPONENT.parent)
if _COMPONENT_DIR not in sys.path:
    sys.path.insert(0, _COMPONENT_DIR)
_AS_SCRIPT = __name__ == "__main__"
if _AS_SCRIPT:
    globals()["__name__"] = "portability_scan"
exec(compile(_COMPONENT.read_text(encoding="utf-8"),
             str(_COMPONENT), "exec"), globals())
if _AS_SCRIPT:
    globals()["__name__"] = "__main__"
    _argv = list(sys.argv[1:])
    if "--root" not in _argv:
        _argv = ["--root", _paths.PACKAGE_ROOT] + _argv
    raise SystemExit(main(_argv))  # noqa: F821 — defined by the exec above
