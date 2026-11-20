"""The config-init command: provision the live config from
the shipped example (contract 04's seed/example pattern).
The live config is untracked and may carry machine-local
values; this verb creates it once and refuses to overwrite
an existing one — provisioning is an install act, performed
while the server is stopped, never an /ops call."""
import os
import sys

from cli import paths as _paths


def cmd_config_init(argv):
    target = _paths.CONFIG_PATH
    example = _paths.CONFIG_EXAMPLE_PATH
    if os.path.exists(target):
        print(f"config-init: live config already exists at {target} "
              "— refusing to overwrite it", file=sys.stderr)
        return 1
    try:
        with open(example, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"config-init: cannot read the example config: {exc}",
              file=sys.stderr)
        return 1
    try:
        with open(target, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        print(f"config-init: cannot write the live config: {exc}",
              file=sys.stderr)
        return 1
    print(f"provisioned the live config at {target} from the shipped "
          "example — edit it for this machine (port, workspace root, "
          "the connector caller registry) before starting the server")
    return 0
