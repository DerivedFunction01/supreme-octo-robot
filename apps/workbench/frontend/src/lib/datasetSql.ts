// A small SQL engine over served dataset tables — the
// mock adapter's half of the dataset console, and the live
// adapter's snapshot fallback when the …/dataset/sql route
// does not answer. It speaks the console's subset:
//
//   SELECT <col, … | *> FROM <table>
//     [WHERE <col> <op> <'text' | number>]
//     [ORDER BY <col> [ASC | DESC]]
//     [LIMIT <n>]
//
// with op one of =, !=, <, >, <=, >=, ~ (contains). Anything
// outside the subset is a refusal with the reason, never a
// silent wrong answer — the same posture the backend
// engine takes toward SQL it cannot run.

import type { DatasetTable } from "./types";

export type SqlOutcome =
  | { ok: true; table: DatasetTable }
  | { ok: false; reason: string };

const OPS = ["<=", ">=", "!=", "=", "<", ">", "~"] as const;

function tokenize(sql: string): string[] {
  const tokens: string[] = [];
  let i = 0;
  while (i < sql.length) {
    const ch = sql[i];
    if (/\s/.test(ch)) {
      i++;
      continue;
    }
    if (ch === "'") {
      const end = sql.indexOf("'", i + 1);
      if (end === -1) throw new Error("unterminated string literal");
      tokens.push(sql.slice(i, end + 1));
      i = end + 1;
      continue;
    }
    if (ch === "," || ch === "*") {
      tokens.push(ch);
      i++;
      continue;
    }
    const op = OPS.find((o) => sql.startsWith(o, i));
    if (op) {
      tokens.push(op);
      i += op.length;
      continue;
    }
    const m = /^[^\s,=*<>!~']+/.exec(sql.slice(i));
    if (!m) throw new Error(`unexpected character: ${ch}`);
    tokens.push(m[0]);
    i += m[0].length;
  }
  return tokens;
}

function compare(cell: string, op: string, literal: string): boolean {
  if (op === "~") return cell.toLowerCase().includes(literal.toLowerCase());
  const cn = Number(cell);
  const ln = Number(literal);
  const numeric = cell.trim() !== "" && !Number.isNaN(cn) && !Number.isNaN(ln);
  const a = numeric ? cn : cell;
  const b = numeric ? ln : literal;
  switch (op) {
    case "=":
      return numeric ? cn === ln : cell === literal;
    case "!=":
      return numeric ? cn !== ln : cell !== literal;
    case "<":
      return a < b;
    case ">":
      return a > b;
    case "<=":
      return a <= b;
    case ">=":
      return a >= b;
    default:
      return false;
  }
}

export function runDatasetSql(tables: DatasetTable[], sql: string): SqlOutcome {
  let tokens: string[];
  try {
    tokens = tokenize(sql.trim().replace(/;$/, ""));
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : String(e) };
  }
  let pos = 0;
  const peek = () => tokens[pos];
  const take = () => tokens[pos++];
  const keyword = (kw: string): boolean => {
    if (peek()?.toUpperCase() === kw) {
      pos++;
      return true;
    }
    return false;
  };
  const need = (kw: string): string | null =>
    keyword(kw) ? null : `expected ${kw}, found ${peek() ?? "end of input"}`;

  if (!keyword("SELECT")) return { ok: false, reason: "only SELECT is supported" };
  const cols: string[] = [];
  let star = false;
  for (;;) {
    const t = take();
    if (t === undefined) return { ok: false, reason: "incomplete SELECT list" };
    if (t === "*") star = true;
    else cols.push(t);
    if (peek() === ",") {
      take();
      continue;
    }
    break;
  }
  const fromErr = need("FROM");
  if (fromErr) return { ok: false, reason: fromErr };
  const tableName = take();
  const table = tables.find(
    (t) => t.name.toLowerCase() === (tableName ?? "").toLowerCase(),
  );
  if (!table) {
    return {
      ok: false,
      reason: `no such table: ${tableName ?? "?"} (served: ${tables.map((t) => t.name).join(", ")})`,
    };
  }
  const colIndex = (name: string): number =>
    table.columns.findIndex((c) => c.toLowerCase() === name.toLowerCase());
  if (!star) {
    for (const c of cols) {
      if (colIndex(c) === -1) return { ok: false, reason: `no such column: ${c}` };
    }
  }

  let rows = table.rows.map((r) => [...r]);

  if (keyword("WHERE")) {
    const col = take();
    const op = take();
    const rawLit = take();
    if (col === undefined || op === undefined || rawLit === undefined) {
      return { ok: false, reason: "incomplete WHERE clause" };
    }
    if (!(OPS as readonly string[]).includes(op)) {
      return { ok: false, reason: `unsupported operator: ${op}` };
    }
    const idx = colIndex(col);
    if (idx === -1) return { ok: false, reason: `no such column: ${col}` };
    const literal = rawLit.startsWith("'") ? rawLit.slice(1, -1) : rawLit;
    rows = rows.filter((r) => compare(r[idx] ?? "", op, literal));
  }

  if (keyword("ORDER")) {
    const byErr = need("BY");
    if (byErr) return { ok: false, reason: byErr };
    const col = take();
    if (col === undefined) return { ok: false, reason: "ORDER BY needs a column" };
    const idx = colIndex(col);
    if (idx === -1) return { ok: false, reason: `no such column: ${col}` };
    let dir = 1;
    if (keyword("DESC")) dir = -1;
    else keyword("ASC");
    rows.sort((a, b) => {
      const an = Number(a[idx]);
      const bn = Number(b[idx]);
      const numeric = !Number.isNaN(an) && !Number.isNaN(bn) && a[idx].trim() !== "";
      const cmp = numeric ? an - bn : (a[idx] ?? "").localeCompare(b[idx] ?? "");
      return cmp * dir;
    });
  }

  if (keyword("LIMIT")) {
    const n = Number(take());
    if (!Number.isInteger(n) || n < 0) return { ok: false, reason: "LIMIT needs a count" };
    rows = rows.slice(0, n);
  }

  if (pos < tokens.length) {
    return { ok: false, reason: `unexpected trailing input: ${tokens.slice(pos).join(" ")}` };
  }

  const outCols = star ? table.columns : cols;
  const idxs = outCols.map((c) => colIndex(c));
  return {
    ok: true,
    table: {
      name: table.name,
      columns: outCols.map((c) => table.columns[colIndex(c)]),
      rows: rows.map((r) => idxs.map((i) => r[i] ?? "")),
    },
  };
}
