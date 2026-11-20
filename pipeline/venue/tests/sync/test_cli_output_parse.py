"""Funnel output-parse units: json_object_from_output reads one
JSON object from CLI exec stdout and ignores whatever trails it
(2026-11-14: the CLI's update nag trailing a probe's object made
launch upload-verifies read as unreadable on landed uploads)."""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli = load("cli", "sync/cli.py")
parse = cli.json_object_from_output

# portability-exception: ~/.config/colab-cli/settings.json — the CLI update nag's own text, reproduced verbatim as the parse fixture: the pins exercise the nag shape exactly as the CLI emits it
NAG = (
    "[colab] A new version of Colab CLI is available: 0.8.0 (current: 0.7.5)\n"
    "[colab] Run 'colab update' to update.\n"
    '[colab] To silence this check, set "enable_update_check": false in ~/.config/colab-cli/settings.json\n'
)


def test_clean_object():
    assert parse('{"size": 42}\n') == {"size": 42}


def test_trailing_update_nag_ignored():
    # The defect as diagnosed: the probe's object, then the banner.
    assert parse('{"size": 42}\n' + NAG) == {"size": 42}


def test_leading_chatter_still_reads_first_object():
    assert parse(NAG + '{"size": 1}\n') == {"size": 1}


def test_second_trailing_value_ignored():
    assert parse('{"a": 1} {"b": 2}\n') == {"a": 1}


def test_nested_object_with_trailing_text():
    out = '{"parts": [{"name": "x", "size": 3}], "size": 3} done\n'
    assert parse(out) == {"parts": [{"name": "x", "size": 3}], "size": 3}


def test_no_brace_is_value_error():
    with pytest.raises(ValueError):
        parse("no json here\n")


def test_truncated_object_is_value_error():
    with pytest.raises(ValueError):
        parse('{"size": ')
