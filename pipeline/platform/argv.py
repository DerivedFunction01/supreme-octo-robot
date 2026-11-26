"""The unified argument parser — the contract home.

Every operator entry point in the tree parses its argv
through this module (the D2 contract of the unified-argv
programme): a tool declares its surface once, as data —
its name, its verbs, each verb's flags and positionals,
its mutually exclusive mode groups — and this module
parses argv against that declaration. No per-tool local
parsing survives beside it; the gate's argv-idioms leg
stands to this module as the writer-uniqueness leg
stands to pipeline/platform/writer.py, its pattern of
record: one homed module, consumers declaring only
their own surface, protocol tests at the home.

The contract, stated once here and nowhere else:

- `--flag value` and `--flag=value` are the same flag.
- An unknown flag, an unknown verb, or a surplus
  positional is a loud refusal — a UsageError the caller
  turns into exit 2 — never silently dropped.
- A value flag missing its value is a usage error,
  never a traceback; a value flag never consumes a
  flag-shaped token in the space form (the `=` form's
  value is explicit and taken literally).
- Flag order never changes semantics: verbs and flags
  are recognised by declaration, not position. (Tools
  whose positional order is itself semantic declare
  their positionals explicitly; it is flag order that
  is free.)
- Safety flags fail closed: a boolean flag given a
  value (`--dry-run=x`), or any near-miss token, is a
  refusal, not the live default.
- A repeated scalar flag is last-wins; a repeatable
  flag accumulates in order.
- Abbreviations are never accepted: a flag token
  matches a declared name exactly, or it is unknown.
- Help text is generated from the same declaration the
  parser consumes, so documentation cannot drift from
  behaviour. `--help` / `-h` before the `--` separator
  yields the generated help and nothing else runs.
- One exit vocabulary: 0 success, 1 operational
  failure, 2 usage. Declared domain verdict codes ride
  the declaration's "verdict_codes" and are the caller's
  business; parsing itself only ever produces 0 or 2.

A declaration is plain data (the JSON shape the bash
and JS adapters consume identically):

    {
      "name": "tool-name",
      "summary": "one line",
      "flags": {"caller": {"takes_value": true,
                           "help": "..."}},
      "positionals": [{"name": "session",
                       "required": true}],
      "verbs": {"acquire": {"flags": {...},
                            "positionals": [...],
                            "mode_groups": [...]}},
      "mode_groups": [{"name": "mode",
                       "flags": ["wait", "poll"],
                       "required": false}],
      "verdict_codes": {"findings": 3}
    }

A flag spec's keys: takes_value (default False),
required, repeatable, safety, default, choices (a list
of permitted values), short (a single character), help.
A positional spec's keys: name, required, variadic
(only the last positional may be variadic), help.

The bash adapter (argv.sh, beside this module) and the
JS adapter (tools/argv.mjs) implement the same contract
over the same declarations; the shared fixture corpus
(argv_fixtures.json) holds all three to it.

Parse-only mode is the programme's proof instrument:
parse_only validates an argv against a declaration and
reports the outcome without executing anything, and
dummy() drives it across a declaration's whole surface.
"""

import json
import sys

USAGE_EXIT = 2


class UsageError(Exception):
    """A parse refusal: the caller prints the message
    with the generated usage and exits USAGE_EXIT."""


class DeclarationError(ValueError):
    """The declaration itself is malformed — a
    programmer error, never a user error."""


_FLAG_SPEC_KEYS = {
    "takes_value", "required", "repeatable", "safety",
    "default", "choices", "short", "help",
}
_POSITIONAL_SPEC_KEYS = {"name", "required", "variadic", "help"}


def _check_flag_specs(flags, where):
    for name, spec in flags.items():
        if not isinstance(spec, dict):
            raise DeclarationError(f"{where}: flag {name!r} spec must be an object")
        unknown = set(spec) - _FLAG_SPEC_KEYS
        if unknown:
            raise DeclarationError(
                f"{where}: flag {name!r} has unknown spec keys {sorted(unknown)}")
        if name.startswith("-") or not name or " " in name or "=" in name:
            raise DeclarationError(f"{where}: bad flag name {name!r}")
        short = spec.get("short")
        if short is not None and (not isinstance(short, str) or len(short) != 1):
            raise DeclarationError(f"{where}: flag {name!r} short must be one character")
        if spec.get("repeatable") and "default" in spec:
            raise DeclarationError(
                f"{where}: repeatable flag {name!r} takes no default")


def _check_positionals(positionals, where):
    names = set()
    for i, spec in enumerate(positionals):
        if not isinstance(spec, dict) or "name" not in spec:
            raise DeclarationError(f"{where}: positional {i} needs a name")
        unknown = set(spec) - _POSITIONAL_SPEC_KEYS
        if unknown:
            raise DeclarationError(
                f"{where}: positional {spec['name']!r} has unknown keys {sorted(unknown)}")
        if spec["name"] in names:
            raise DeclarationError(f"{where}: duplicate positional {spec['name']!r}")
        names.add(spec["name"])
        if spec.get("variadic") and i != len(positionals) - 1:
            raise DeclarationError(
                f"{where}: variadic positional {spec['name']!r} must be last")


def _check_mode_groups(groups, flags, where):
    for group in groups:
        for name in group.get("flags", []):
            if name not in flags:
                raise DeclarationError(
                    f"{where}: mode group {group.get('name')!r} names "
                    f"undeclared flag {name!r}")
            if flags[name].get("takes_value"):
                raise DeclarationError(
                    f"{where}: mode group flag {name!r} must be boolean")


def validate_declaration(decl):
    """Raise DeclarationError unless decl is a well-formed
    surface declaration. A flag name carries one shape
    across every scope that declares it, so the verb
    pre-scan's union is never ambiguous."""
    if not isinstance(decl, dict) or not decl.get("name"):
        raise DeclarationError("declaration needs a name")
    shapes = {}

    def note(flags, where):
        _check_flag_specs(flags, where)
        for name, spec in flags.items():
            shape = (bool(spec.get("takes_value")), bool(spec.get("repeatable")))
            if name in shapes and shapes[name] != shape:
                raise DeclarationError(
                    f"flag {name!r} declared with divergent shapes "
                    f"({where} vs an earlier scope)")
            shapes[name] = shape

    global_flags = decl.get("flags", {})
    note(global_flags, decl["name"])
    _check_positionals(decl.get("positionals", []), decl["name"])
    _check_mode_groups(decl.get("mode_groups", []), global_flags, decl["name"])
    verbs = decl.get("verbs", {})
    if verbs and decl.get("positionals"):
        raise DeclarationError(
            f"{decl['name']}: a verb tool declares positionals per verb, "
            "not at the top level")
    for verb, vspec in verbs.items():
        where = f"{decl['name']} {verb}"
        vflags = vspec.get("flags", {})
        note(vflags, where)
        _check_positionals(vspec.get("positionals", []), where)
        merged = dict(global_flags)
        merged.update(vflags)
        _check_mode_groups(vspec.get("mode_groups", []), merged, where)
    return decl


def _flag_shaped(token, short_names):
    """A token a value flag must never consume in the
    space form: a long-flag form, a declared short form,
    or the separator itself."""
    if token == "--" or token.startswith("--"):
        return True
    if len(token) >= 2 and token[0] == "-" and token[1] in short_names:
        return True
    return token in ("-h",)


def _find_verb(decl, head):
    """The verb is the first bare token, recognised by
    declaration: flag tokens and the values of union
    value flags are skipped, in either value form."""
    verbs = decl.get("verbs", {})
    if not verbs:
        return None
    union = {}
    for spec in [decl.get("flags", {})] + [
            v.get("flags", {}) for v in verbs.values()]:
        union.update(spec)
    shorts = {s["short"] for s in union.values() if s.get("short")}
    i = 0
    while i < len(head):
        token = head[i]
        if token.startswith("--"):
            name = token[2:].split("=", 1)[0]
            spec = union.get(name)
            if (spec is not None and spec.get("takes_value")
                    and "=" not in token):
                i += 2
            else:
                i += 1
            continue
        if len(token) >= 2 and token[0] == "-" and token[1] in shorts:
            spec = next(s for s in union.values()
                        if s.get("short") == token[1])
            i += 2 if (spec.get("takes_value") and "=" not in token
                        and len(token) == 2) else 1
            continue
        return token
    return None


def parse(decl, argv):
    """Parse argv (no program name) against decl.
    Returns {"verb", "flags", "positionals", "present"}
    — or {"help": text} when help was requested.
    Raises UsageError on any refusal."""
    validate_declaration(decl)
    argv = list(argv)
    if "--" in argv:
        cut = argv.index("--")
        head, tail = argv[:cut], argv[cut + 1:]
    else:
        head, tail = argv, []
    if "--help" in head or "-h" in head:
        return {"help": help_text(decl, _find_verb(decl, head))}
    verbs = decl.get("verbs", {})
    verb = None
    if verbs:
        verb = _find_verb(decl, head)
        if verb is None:
            raise UsageError(
                f"{decl['name']}: a verb is required "
                f"({'|'.join(sorted(verbs))})")
        if verb not in verbs:
            raise UsageError(f"{decl['name']}: unknown verb {verb!r}")
    vspec = verbs.get(verb, {}) if verb else {}
    flags_decl = dict(decl.get("flags", {}))
    flags_decl.update(vspec.get("flags", {}))
    shorts = {}
    for name, spec in flags_decl.items():
        if spec.get("short"):
            shorts[spec["short"]] = name
    values = {}
    present = []
    bare = []
    verb_seen = verb is None
    i = 0
    while i < len(head):
        token = head[i]
        if not verb_seen and token == verb:
            verb_seen = True
            i += 1
            continue
        if token.startswith("--"):
            body = token[2:]
            name, eq, attached = body.partition("=")
            spec = flags_decl.get(name)
            if spec is None:
                raise UsageError(f"{decl['name']}: unknown flag --{name}")
            if spec.get("takes_value"):
                if eq:
                    value = attached
                else:
                    if i + 1 >= len(head) or _flag_shaped(head[i + 1], shorts):
                        raise UsageError(
                            f"{decl['name']}: flag --{name} needs a value")
                    value = head[i + 1]
                    i += 1
                _store(values, present, name, spec, value, decl)
            else:
                if eq:
                    raise UsageError(
                        f"{decl['name']}: flag --{name} takes no value")
                _store(values, present, name, spec, True, decl)
            i += 1
            continue
        if len(token) >= 2 and token[0] == "-" and token[1] in shorts:
            name = shorts[token[1]]
            spec = flags_decl[name]
            rest = token[2:]
            if spec.get("takes_value"):
                if rest.startswith("="):
                    value = rest[1:]
                elif rest:
                    value = rest
                else:
                    if i + 1 >= len(head) or _flag_shaped(head[i + 1], shorts):
                        raise UsageError(
                            f"{decl['name']}: flag --{name} needs a value")
                    value = head[i + 1]
                    i += 1
                _store(values, present, name, spec, value, decl)
            else:
                if rest:
                    raise UsageError(
                        f"{decl['name']}: unknown flag {token}")
                _store(values, present, name, spec, True, decl)
            i += 1
            continue
        if token.startswith("-") and token != "-":
            raise UsageError(f"{decl['name']}: unknown flag {token}")
        bare.append(token)
        i += 1
    bare.extend(tail)
    positionals = _assign_positionals(
        decl, vspec.get("positionals", decl.get("positionals", [])), bare)
    for name, spec in flags_decl.items():
        if name not in values:
            if spec.get("required"):
                raise UsageError(
                    f"{decl['name']}: flag --{name} is required")
            values[name] = (list() if spec.get("repeatable")
                            else spec.get("default", None)
                            if spec.get("takes_value") else False)
    groups = list(decl.get("mode_groups", [])) + list(vspec.get("mode_groups", []))
    for group in groups:
        chosen = [n for n in group["flags"] if n in present]
        if len(chosen) > 1:
            raise UsageError(
                f"{decl['name']}: mode group {group['name']!r} takes one of "
                f"{group['flags']}; got {chosen}")
        if group.get("required") and not chosen:
            raise UsageError(
                f"{decl['name']}: mode group {group['name']!r} requires "
                f"one of {group['flags']}")
    return {"verb": verb, "flags": values,
            "positionals": positionals, "present": sorted(present)}


def _store(values, present, name, spec, value, decl):
    if spec.get("choices") is not None and value not in spec["choices"]:
        raise UsageError(
            f"{decl['name']}: flag --{name} takes one of "
            f"{spec['choices']}; got {value!r}")
    if name not in present:
        present.append(name)
    if spec.get("repeatable"):
        if spec.get("takes_value"):
            values.setdefault(name, []).append(value)
        else:
            values[name] = values.get(name, 0) + 1
    else:
        values[name] = value  # last wins


def _assign_positionals(decl, specs, bare):
    out = {}
    idx = 0
    for spec in specs:
        name = spec["name"]
        if spec.get("variadic"):
            out[name] = bare[idx:]
            idx = len(bare)
        elif idx < len(bare):
            out[name] = bare[idx]
            idx += 1
        elif spec.get("required"):
            raise UsageError(
                f"{decl['name']}: positional {name} is required")
        else:
            out[name] = None
    if idx < len(bare):
        raise UsageError(
            f"{decl['name']}: surplus positional {bare[idx]!r}")
    return out


def _flag_usage(name, spec):
    form = f"--{name}"
    if spec.get("short"):
        form += f"|-{spec['short']}"
    if spec.get("takes_value"):
        form += " VALUE"
    return form


def help_text(decl, verb=None):
    """The generated help: the same declaration the
    parser consumes, rendered — it cannot drift."""
    validate_declaration(decl)
    lines = []
    verbs = decl.get("verbs", {})
    if verb is not None and verb in verbs:
        vspec = verbs[verb]
        lines.append(f"usage: {decl['name']} {verb} [flags]")
        if vspec.get("summary"):
            lines.append(vspec["summary"])
        _help_body(lines, decl, vspec)
        return "\n".join(lines) + "\n"
    usage = f"usage: {decl['name']}"
    if verbs:
        usage += f" <{'|'.join(sorted(verbs))}> [flags]"
    elif decl.get("positionals"):
        usage += " " + " ".join(
            f"<{p['name']}>" if p.get("required") else f"[{p['name']}]"
            for p in decl["positionals"])
    else:
        usage += " [flags]"
    lines.append(usage)
    if decl.get("summary"):
        lines.append(decl["summary"])
    if verbs:
        lines.append("verbs:")
        for name in sorted(verbs):
            lines.append(f"  {name}  {verbs[name].get('summary', '')}".rstrip())
    _help_body(lines, decl, decl)
    for name in sorted(verbs):
        if verbs[name].get("flags") or verbs[name].get("positionals"):
            lines.append(f"verb {name}:")
            _help_body(lines, dict(decl, flags={}), verbs[name])
    codes = decl.get("verdict_codes")
    if codes:
        lines.append("verdict codes: " + ", ".join(
            f"{k}={v}" for k, v in sorted(codes.items())))
    return "\n".join(lines) + "\n"


def _help_body(lines, decl, spec):
    flags = dict(decl.get("flags", {}))
    if spec is not decl:
        flags.update(spec.get("flags", {}))
    if flags:
        lines.append("flags:")
        for name in sorted(flags):
            fspec = flags[name]
            bits = [_flag_usage(name, fspec)]
            if fspec.get("required"):
                bits.append("(required)")
            if fspec.get("repeatable"):
                bits.append("(repeatable)")
            if fspec.get("safety"):
                bits.append("(safety: fails closed)")
            if fspec.get("help"):
                bits.append(f"— {fspec['help']}")
            lines.append("  " + " ".join(bits))
    positionals = spec.get("positionals", [])
    if positionals:
        lines.append("positionals:")
        for pspec in positionals:
            bits = [pspec["name"]]
            if pspec.get("required"):
                bits.append("(required)")
            if pspec.get("variadic"):
                bits.append("(variadic)")
            if pspec.get("help"):
                bits.append(f"— {pspec['help']}")
            lines.append("  " + " ".join(bits))
    groups = list(decl.get("mode_groups", []))
    if spec is not decl:
        groups += spec.get("mode_groups", [])
    for group in groups:
        lines.append(
            f"mode group {group['name']}: one of "
            + ", ".join(f"--{n}" for n in group["flags"])
            + (" (required)" if group.get("required") else ""))


def parse_only(decl, argv):
    """Validate argv against decl and report the parse
    without executing anything: {"ok", "exit_code",
    "result"|"help"|"error", "usage" on refusal}."""
    try:
        result = parse(decl, argv)
    except UsageError as exc:
        return {"ok": False, "exit_code": USAGE_EXIT,
                "error": str(exc), "usage": help_text(decl)}
    if "help" in result:
        return {"ok": True, "exit_code": 0, "help": result["help"]}
    return {"ok": True, "exit_code": 0, "result": result}


def _scope_cases(decl, verb, vspec):
    """The dummy battery for one scope: the minimal valid
    invocation, each flag in both forms, and the refusal
    forms — each tagged with its expected outcome. A
    verb tool's top level has no valid verb-less
    invocation: its battery is the refusal and the help."""
    if verb is None and decl.get("verbs"):
        return [{"argv": [], "expect_ok": False},
                {"argv": ["--help"], "expect_ok": True}]
    flags = dict(decl.get("flags", {}))
    flags.update(vspec.get("flags", {}))
    prefix = [verb] if verb else []
    base = list(prefix)
    for name, spec in flags.items():
        if spec.get("required") and spec.get("takes_value"):
            base += [f"--{name}",
                     spec["choices"][0] if spec.get("choices") else "x"]
    for pspec in vspec.get("positionals", decl.get("positionals", [])):
        if pspec.get("required") and not pspec.get("variadic"):
            base.append("x")
    cases = [{"argv": base, "expect_ok": True}]
    for name, spec in flags.items():
        if spec.get("takes_value"):
            value = spec["choices"][0] if spec.get("choices") else "y"
            cases.append({"argv": base + [f"--{name}", value],
                          "expect_ok": True})
            cases.append({"argv": base + [f"--{name}={value}"],
                          "expect_ok": True})
            cases.append({"argv": base + [f"--{name}"],
                          "expect_ok": False})
            cases.append({"argv": base + [f"--{name}", "--help-x"],
                          "expect_ok": False})
        else:
            cases.append({"argv": base + [f"--{name}"],
                          "expect_ok": True})
            cases.append({"argv": base + [f"--{name}=y"],
                          "expect_ok": False})
    cases.append({"argv": base + ["--bogus-flag"], "expect_ok": False})
    cases.append({"argv": base + ["--help"], "expect_ok": True})
    groups = list(decl.get("mode_groups", [])) + list(
        vspec.get("mode_groups", []))
    for group in groups:
        if len(group["flags"]) >= 2:
            cases.append({
                "argv": base + [f"--{group['flags'][0]}",
                                f"--{group['flags'][1]}"],
                "expect_ok": False})
    return cases


def dummy(decl):
    """Drive parse_only across the declaration's whole
    surface — the top level and every verb — and report
    each case with whether the outcome matched its
    expectation. The dummy runner of the proof method:
    parse-only invocations, nothing executes."""
    validate_declaration(decl)
    scopes = [(None, decl)]
    for verb, vspec in decl.get("verbs", {}).items():
        scopes.append((verb, vspec))
    out = []
    for verb, vspec in scopes:
        for case in _scope_cases(decl, verb, vspec):
            outcome = parse_only(decl, case["argv"])
            out.append({
                "verb": verb, "argv": case["argv"],
                "expect_ok": case["expect_ok"],
                "ok": outcome["ok"],
                "matched": outcome["ok"] == case["expect_ok"],
                "outcome": outcome,
            })
    return out


def main(argv):
    """argv.py <declaration.json> dummy | <argv...>

    dummy runs the parse-only battery over the
    declaration and exits 0 when every case matches;
    any other argument list is parsed (parse-only) and
    its outcome printed as JSON, exiting with the
    outcome's exit code."""
    if len(argv) < 2:
        print("usage: argv.py <declaration.json> dummy|<argv...>",
              file=sys.stderr)
        return USAGE_EXIT
    with open(argv[0], encoding="utf-8") as fh:
        decl = json.load(fh)
    if argv[1] == "dummy":
        cases = dummy(decl)
        bad = [c for c in cases if not c["matched"]]
        print(json.dumps({"cases": len(cases),
                          "mismatched": len(bad)}, indent=2))
        return 1 if bad else 0
    outcome = parse_only(decl, argv[1:])
    print(json.dumps(outcome, indent=2, default=str))
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
