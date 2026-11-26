#!/usr/bin/env node
// The unified argument parser — the JS adapter.
//
// A thin local adapter over the one contract home,
// pipeline/platform/argv.py: the same declaration data,
// the same clauses, held to them by the shared fixture
// corpus (pipeline/platform/argv_fixtures.json), which
// this module runs in its `corpus` mode. The contract,
// stated once in the home module and nowhere else:
// both value forms are one flag; unknown flags, unknown
// verbs, and surplus positionals refuse (usage, exit
// 2); a value flag missing its value, or handed a
// flag-shaped token in the space form, is a usage
// error, never a crash; flag order never changes
// semantics; safety flags fail closed; a repeated
// scalar flag is last-wins; abbreviations are never
// accepted; help is generated from the declaration.
//
// Usage (module form): import { parseArgv, parseOnly,
// helpText, UsageError } from "./argv.mjs"
// Usage (CLI form): argv.mjs corpus <fixtures.json>
//   argv.mjs parse <declaration.json> <argv...>

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const USAGE_EXIT = 2;

export class UsageError extends Error {}
class DeclarationError extends Error {}

const FLAG_SPEC_KEYS = new Set([
  "takes_value", "required", "repeatable", "safety",
  "default", "choices", "short", "help",
]);
const POSITIONAL_SPEC_KEYS = new Set([
  "name", "required", "variadic", "help",
]);

function checkFlagSpecs(flags, where, shapes) {
  for (const [name, spec] of Object.entries(flags)) {
    if (typeof spec !== "object" || spec === null)
      throw new DeclarationError(`${where}: flag ${name} spec must be an object`);
    for (const key of Object.keys(spec))
      if (!FLAG_SPEC_KEYS.has(key))
        throw new DeclarationError(`${where}: flag ${name} has unknown spec key ${key}`);
    if (name.startsWith("-") || !name || name.includes(" ") || name.includes("="))
      throw new DeclarationError(`${where}: bad flag name ${name}`);
    if (spec.short !== undefined && (typeof spec.short !== "string" || spec.short.length !== 1))
      throw new DeclarationError(`${where}: flag ${name} short must be one character`);
    if (spec.repeatable && "default" in spec)
      throw new DeclarationError(`${where}: repeatable flag ${name} takes no default`);
    const shape = `${!!spec.takes_value}/${!!spec.repeatable}`;
    if (shapes.has(name) && shapes.get(name) !== shape)
      throw new DeclarationError(`flag ${name} declared with divergent shapes`);
    shapes.set(name, shape);
  }
}

function checkPositionals(positionals, where) {
  const names = new Set();
  positionals.forEach((spec, i) => {
    if (typeof spec !== "object" || spec === null || !("name" in spec))
      throw new DeclarationError(`${where}: positional ${i} needs a name`);
    for (const key of Object.keys(spec))
      if (!POSITIONAL_SPEC_KEYS.has(key))
        throw new DeclarationError(`${where}: positional ${spec.name} has unknown key ${key}`);
    if (names.has(spec.name))
      throw new DeclarationError(`${where}: duplicate positional ${spec.name}`);
    names.add(spec.name);
    if (spec.variadic && i !== positionals.length - 1)
      throw new DeclarationError(`${where}: variadic positional ${spec.name} must be last`);
  });
}

function checkModeGroups(groups, flags, where) {
  for (const group of groups) {
    for (const name of group.flags ?? []) {
      if (!(name in flags))
        throw new DeclarationError(`${where}: mode group ${group.name} names undeclared flag ${name}`);
      if (flags[name].takes_value)
        throw new DeclarationError(`${where}: mode group flag ${name} must be boolean`);
    }
  }
}

export function validateDeclaration(decl) {
  if (typeof decl !== "object" || decl === null || !decl.name)
    throw new DeclarationError("declaration needs a name");
  const shapes = new Map();
  const globalFlags = decl.flags ?? {};
  checkFlagSpecs(globalFlags, decl.name, shapes);
  checkPositionals(decl.positionals ?? [], decl.name);
  checkModeGroups(decl.mode_groups ?? [], globalFlags, decl.name);
  const verbs = decl.verbs ?? {};
  if (Object.keys(verbs).length && (decl.positionals ?? []).length)
    throw new DeclarationError(`${decl.name}: a verb tool declares positionals per verb`);
  for (const [verb, vspec] of Object.entries(verbs)) {
    const where = `${decl.name} ${verb}`;
    const vflags = vspec.flags ?? {};
    checkFlagSpecs(vflags, where, shapes);
    checkPositionals(vspec.positionals ?? [], where);
    checkModeGroups(vspec.mode_groups ?? [], { ...globalFlags, ...vflags }, where);
  }
  return decl;
}

function flagShaped(token, shorts) {
  if (token === "--" || token.startsWith("--")) return true;
  if (token.length >= 2 && token[0] === "-" && shorts.has(token[1])) return true;
  return token === "-h";
}

function findVerb(decl, head) {
  const verbs = decl.verbs ?? {};
  if (!Object.keys(verbs).length) return null;
  const union = {};
  Object.assign(union, decl.flags ?? {});
  for (const v of Object.values(verbs)) Object.assign(union, v.flags ?? {});
  const shorts = new Set(
    Object.values(union).filter((s) => s.short).map((s) => s.short));
  let i = 0;
  while (i < head.length) {
    const token = head[i];
    if (token.startsWith("--")) {
      const name = token.slice(2).split("=", 1)[0];
      const spec = union[name];
      i += spec && spec.takes_value && !token.includes("=") ? 2 : 1;
      continue;
    }
    if (token.length >= 2 && token[0] === "-" && shorts.has(token[1])) {
      const spec = Object.values(union).find((s) => s.short === token[1]);
      i += spec.takes_value && !token.includes("=") && token.length === 2 ? 2 : 1;
      continue;
    }
    return token;
  }
  return null;
}

function store(values, present, name, spec, value, decl) {
  if (spec.choices !== undefined && !spec.choices.includes(value))
    throw new UsageError(
      `${decl.name}: flag --${name} takes one of ${JSON.stringify(spec.choices)}; got ${JSON.stringify(value)}`);
  if (!present.includes(name)) present.push(name);
  if (spec.repeatable) {
    if (spec.takes_value) {
      if (!(name in values)) values[name] = [];
      values[name].push(value);
    } else {
      values[name] = (values[name] ?? 0) + 1;
    }
  } else {
    values[name] = value; // last wins
  }
}

function assignPositionals(decl, specs, bare) {
  const out = {};
  let idx = 0;
  for (const spec of specs) {
    if (spec.variadic) {
      out[spec.name] = bare.slice(idx);
      idx = bare.length;
    } else if (idx < bare.length) {
      out[spec.name] = bare[idx];
      idx += 1;
    } else if (spec.required) {
      throw new UsageError(`${decl.name}: positional ${spec.name} is required`);
    } else {
      out[spec.name] = null;
    }
  }
  if (idx < bare.length)
    throw new UsageError(`${decl.name}: surplus positional ${JSON.stringify(bare[idx])}`);
  return out;
}

export function parseArgv(decl, argv) {
  validateDeclaration(decl);
  argv = [...argv];
  const cut = argv.indexOf("--");
  const head = cut >= 0 ? argv.slice(0, cut) : argv;
  const tail = cut >= 0 ? argv.slice(cut + 1) : [];
  if (head.includes("--help") || head.includes("-h"))
    return { help: helpText(decl, findVerb(decl, head)) };
  const verbs = decl.verbs ?? {};
  let verb = null;
  if (Object.keys(verbs).length) {
    verb = findVerb(decl, head);
    if (verb === null)
      throw new UsageError(
        `${decl.name}: a verb is required (${Object.keys(verbs).sort().join("|")})`);
    if (!(verb in verbs))
      throw new UsageError(`${decl.name}: unknown verb ${JSON.stringify(verb)}`);
  }
  const vspec = verb ? verbs[verb] : {};
  const flagsDecl = { ...(decl.flags ?? {}), ...(vspec.flags ?? {}) };
  const shorts = new Map();
  for (const [name, spec] of Object.entries(flagsDecl))
    if (spec.short) shorts.set(spec.short, name);
  const values = {};
  const present = [];
  const bare = [];
  let verbSeen = verb === null;
  let i = 0;
  while (i < head.length) {
    const token = head[i];
    if (!verbSeen && token === verb) { verbSeen = true; i += 1; continue; }
    if (token.startsWith("--")) {
      const body = token.slice(2);
      const eq = body.indexOf("=");
      const name = eq >= 0 ? body.slice(0, eq) : body;
      const spec = flagsDecl[name];
      if (spec === undefined)
        throw new UsageError(`${decl.name}: unknown flag --${name}`);
      if (spec.takes_value) {
        let value;
        if (eq >= 0) {
          value = body.slice(eq + 1);
        } else {
          if (i + 1 >= head.length || flagShaped(head[i + 1], new Set(shorts.keys())))
            throw new UsageError(`${decl.name}: flag --${name} needs a value`);
          value = head[i + 1];
          i += 1;
        }
        store(values, present, name, spec, value, decl);
      } else {
        if (eq >= 0)
          throw new UsageError(`${decl.name}: flag --${name} takes no value`);
        store(values, present, name, spec, true, decl);
      }
      i += 1;
      continue;
    }
    if (token.length >= 2 && token[0] === "-" && shorts.has(token[1])) {
      const name = shorts.get(token[1]);
      const spec = flagsDecl[name];
      const rest = token.slice(2);
      if (spec.takes_value) {
        let value;
        if (rest.startsWith("=")) value = rest.slice(1);
        else if (rest) value = rest;
        else {
          if (i + 1 >= head.length || flagShaped(head[i + 1], new Set(shorts.keys())))
            throw new UsageError(`${decl.name}: flag --${name} needs a value`);
          value = head[i + 1];
          i += 1;
        }
        store(values, present, name, spec, value, decl);
      } else {
        if (rest) throw new UsageError(`${decl.name}: unknown flag ${token}`);
        store(values, present, name, spec, true, decl);
      }
      i += 1;
      continue;
    }
    if (token.startsWith("-") && token !== "-")
      throw new UsageError(`${decl.name}: unknown flag ${token}`);
    bare.push(token);
    i += 1;
  }
  bare.push(...tail);
  const positionals = assignPositionals(
    decl, vspec.positionals ?? decl.positionals ?? [], bare);
  for (const [name, spec] of Object.entries(flagsDecl)) {
    if (!(name in values)) {
      if (spec.required)
        throw new UsageError(`${decl.name}: flag --${name} is required`);
      values[name] = spec.repeatable ? []
        : spec.takes_value ? ("default" in spec ? spec.default : null) : false;
    }
  }
  const groups = [...(decl.mode_groups ?? []), ...(vspec.mode_groups ?? [])];
  for (const group of groups) {
    const chosen = group.flags.filter((n) => present.includes(n));
    if (chosen.length > 1)
      throw new UsageError(
        `${decl.name}: mode group ${JSON.stringify(group.name)} takes one of ${JSON.stringify(group.flags)}; got ${JSON.stringify(chosen)}`);
    if (group.required && !chosen.length)
      throw new UsageError(
        `${decl.name}: mode group ${JSON.stringify(group.name)} requires one of ${JSON.stringify(group.flags)}`);
  }
  return { verb, flags: values, positionals, present: [...present].sort() };
}

function flagUsage(name, spec) {
  let form = `--${name}`;
  if (spec.short) form += `|-${spec.short}`;
  if (spec.takes_value) form += " VALUE";
  return form;
}

function helpBody(lines, decl, spec) {
  const flags = { ...(decl.flags ?? {}), ...(spec === decl ? {} : spec.flags ?? {}) };
  if (Object.keys(flags).length) {
    lines.push("flags:");
    for (const name of Object.keys(flags).sort()) {
      const fspec = flags[name];
      const bits = [flagUsage(name, fspec)];
      if (fspec.required) bits.push("(required)");
      if (fspec.repeatable) bits.push("(repeatable)");
      if (fspec.safety) bits.push("(safety: fails closed)");
      if (fspec.help) bits.push(`— ${fspec.help}`);
      lines.push("  " + bits.join(" "));
    }
  }
  const positionals = spec.positionals ?? [];
  if (positionals.length) {
    lines.push("positionals:");
    for (const pspec of positionals) {
      const bits = [pspec.name];
      if (pspec.required) bits.push("(required)");
      if (pspec.variadic) bits.push("(variadic)");
      if (pspec.help) bits.push(`— ${pspec.help}`);
      lines.push("  " + bits.join(" "));
    }
  }
  const groups = [...(decl.mode_groups ?? []),
    ...(spec === decl ? [] : spec.mode_groups ?? [])];
  for (const group of groups)
    lines.push(`mode group ${group.name}: one of `
      + group.flags.map((n) => `--${n}`).join(", ")
      + (group.required ? " (required)" : ""));
}

export function helpText(decl, verb = null) {
  validateDeclaration(decl);
  const lines = [];
  const verbs = decl.verbs ?? {};
  if (verb !== null && verb in verbs) {
    const vspec = verbs[verb];
    lines.push(`usage: ${decl.name} ${verb} [flags]`);
    if (vspec.summary) lines.push(vspec.summary);
    helpBody(lines, decl, vspec);
    return lines.join("\n") + "\n";
  }
  let usage = `usage: ${decl.name}`;
  if (Object.keys(verbs).length)
    usage += ` <${Object.keys(verbs).sort().join("|")}> [flags]`;
  else if ((decl.positionals ?? []).length)
    usage += " " + decl.positionals
      .map((p) => (p.required ? `<${p.name}>` : `[${p.name}]`)).join(" ");
  else usage += " [flags]";
  lines.push(usage);
  if (decl.summary) lines.push(decl.summary);
  if (Object.keys(verbs).length) {
    lines.push("verbs:");
    for (const name of Object.keys(verbs).sort())
      lines.push(`  ${name}  ${verbs[name].summary ?? ""}`.trimEnd());
  }
  helpBody(lines, decl, decl);
  for (const name of Object.keys(verbs).sort())
    if (Object.keys(verbs[name].flags ?? {}).length
        || (verbs[name].positionals ?? []).length) {
      lines.push(`verb ${name}:`);
      helpBody(lines, { ...decl, flags: {} }, verbs[name]);
    }
  if (decl.verdict_codes)
    lines.push("verdict codes: " + Object.entries(decl.verdict_codes)
      .sort().map(([k, v]) => `${k}=${v}`).join(", "));
  return lines.join("\n") + "\n";
}

export function parseOnly(decl, argv) {
  try {
    const result = parseArgv(decl, argv);
    if ("help" in result)
      return { ok: true, exit_code: 0, help: result.help };
    return { ok: true, exit_code: 0, result };
  } catch (exc) {
    if (exc instanceof UsageError)
      return { ok: false, exit_code: USAGE_EXIT, error: exc.message,
               usage: helpText(decl) };
    throw exc;
  }
}

function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (typeof a === "object") {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    return ka.every((k) => k in b && deepEqual(a[k], b[k]));
  }
  return false;
}

export function runCorpus(fixtures) {
  const failures = [];
  fixtures.vectors.forEach((vector, idx) => {
    const decl = fixtures.declarations[vector.decl];
    const outcome = parseOnly(decl, vector.argv);
    const expect = vector.expect;
    let matched;
    if (!expect.ok) matched = !outcome.ok;
    else if (expect.help) matched = outcome.ok && "help" in outcome;
    else matched = outcome.ok && "result" in outcome
      && outcome.result.verb === (expect.verb ?? null)
      && deepEqual(outcome.result.flags, expect.flags)
      && deepEqual(outcome.result.positionals, expect.positionals);
    if (!matched)
      failures.push({ index: idx, vector, outcome: JSON.stringify(outcome) });
  });
  return failures;
}

function main(argv) {
  if (argv[0] === "corpus" && argv.length === 2) {
    const fixtures = JSON.parse(readFileSync(argv[1], "utf8"));
    const failures = runCorpus(fixtures);
    for (const failure of failures)
      console.error(`vector ${failure.index}: ${JSON.stringify(failure.vector)} -> ${failure.outcome}`);
    console.log(`argv corpus: ${fixtures.vectors.length - failures.length}/${fixtures.vectors.length} vectors matched`);
    return failures.length ? 1 : 0;
  }
  if (argv[0] === "parse" && argv.length >= 2) {
    const decl = JSON.parse(readFileSync(argv[1], "utf8"));
    const outcome = parseOnly(decl, argv.slice(2));
    console.log(JSON.stringify(outcome, null, 2));
    return outcome.exit_code;
  }
  console.error("usage: argv.mjs corpus <fixtures.json> | parse <declaration.json> <argv...>");
  return USAGE_EXIT;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1])
  process.exit(main(process.argv.slice(2)));
