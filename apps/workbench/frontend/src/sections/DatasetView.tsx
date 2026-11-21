import { useMemo, useState } from "react";
import { DataTable } from "@kit/components/display/DataTable";
import { Button } from "@kit/components/controls/Button";
import { useAdapter } from "../lib/store";
import type { DatasetTable, RepoFile } from "../lib/types";
import { Group, GroupLabel, Lab, Row, Sub, Val } from "../components/ui";

// Dataset depth (W11): the peek's table tab grown into the
// original's dataset surface — table select over the
// file's served tables, a column filter, sorting,
// pagination, numeric column stats, and the SQL console
// over the dataset SQL route (the repos POST dispatch —
// run_dataset_sql server-side; the snapshot engine answers
// when the route is not there, and says so).

const PAGE_SIZE = 10;

const inputStyle: React.CSSProperties = {
  backgroundColor: "var(--wb-surface-sunken)",
  color: "var(--wb-content-primary)",
  borderRadius: 9,
  padding: "6px 10px",
  fontSize: 13.5,
};

function numericStats(table: DatasetTable): { column: string; min: number; max: number; avg: number }[] {
  const out: { column: string; min: number; max: number; avg: number }[] = [];
  table.columns.forEach((col, ci) => {
    const values = table.rows.map((r) => r[ci]).filter((v) => v !== "" && v !== undefined);
    if (values.length === 0) return;
    const nums = values.map((v) => Number(v));
    if (nums.some((n) => Number.isNaN(n))) return;
    out.push({
      column: col,
      min: Math.min(...nums),
      max: Math.max(...nums),
      avg: Math.round((nums.reduce((a, b) => a + b, 0) / nums.length) * 100) / 100,
    });
  });
  return out;
}

export function DatasetView({
  repoSlug,
  path,
  file,
}: {
  repoSlug: string;
  path: string;
  file: RepoFile;
}) {
  const a = useAdapter();
  const tables = file.dataset?.tables ?? [];
  const [tableName, setTableName] = useState(tables[0]?.name ?? "");
  const table = tables.find((t) => t.name === tableName) ?? tables[0];
  const [filterColumn, setFilterColumn] = useState("");
  const [filterText, setFilterText] = useState("");
  const [sortColumn, setSortColumn] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(0);
  const [sql, setSql] = useState("");
  const [sqlBusy, setSqlBusy] = useState(false);
  const [sqlResult, setSqlResult] = useState<
    | { ok: true; table: DatasetTable; source: "engine" | "snapshot" }
    | { ok: false; reason: string }
    | null
  >(null);

  const shown = useMemo(() => {
    if (!table) return [];
    let rows = table.rows;
    if (filterColumn && filterText.trim()) {
      const ci = table.columns.indexOf(filterColumn);
      const needle = filterText.trim().toLowerCase();
      rows = rows.filter((r) => (r[ci] ?? "").toLowerCase().includes(needle));
    }
    if (sortColumn) {
      const ci = table.columns.indexOf(sortColumn);
      const numeric = rows.every((r) => r[ci] === "" || !Number.isNaN(Number(r[ci])));
      rows = [...rows].sort((x, y) => {
        const cmp = numeric
          ? Number(x[ci] || 0) - Number(y[ci] || 0)
          : (x[ci] ?? "").localeCompare(y[ci] ?? "");
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return rows;
  }, [table, filterColumn, filterText, sortColumn, sortDir]);

  if (!table) {
    return (
      <p className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
        No dataset is served for this file.
      </p>
    );
  }

  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const pageRows = shown.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const stats = numericStats(table);

  const runSql = async () => {
    if (!sql.trim()) return;
    setSqlBusy(true);
    try {
      const out = await a.datasetSql(repoSlug, path, sql);
      setSqlResult(out.ok ? { ok: true, table: out.table, source: out.source } : out);
    } finally {
      setSqlBusy(false);
    }
  };

  const gridFor = (t: DatasetTable, rows: string[][], label: string) => (
    <div
      // The kit table is w-full table-fixed with equal
      // columns: without a floor it compresses to the phone
      // viewport and every cell ellipsizes (accession IDs
      // unreadable at 88px columns, mobile critic
      // 2026-11-15). The per-column floor (220px — an
      // accession number plus cell padding) keeps values
      // whole; the box scrolls horizontally to reach them.
      className="overflow-x-auto"
      style={{
        backgroundColor: "var(--wb-surface-2)",
        border: "1px solid var(--wb-border-default)",
        borderRadius: "var(--wb-radius-lg)",
      }}
    >
      <div style={{ minWidth: Math.max(560, t.columns.length * 220) }}>
        <DataTable
          ariaLabel={label}
          columns={t.columns.map((c) => ({ key: c, header: c }))}
          rows={rows.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i] ?? ""])))}
          rowKey={(r) => t.columns.map((c) => String(r[c])).join("|")}
        />
      </div>
    </div>
  );

  return (
    <div>
      {tables.length > 1 ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-semibold" style={{ color: "var(--wb-content-secondary)" }}>
            Table
          </span>
          <select
            aria-label="Dataset table"
            value={table.name}
            onChange={(e) => {
              setTableName(e.target.value);
              setPage(0);
              setFilterColumn("");
              setSortColumn("");
            }}
            style={inputStyle}
          >
            {tables.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name} · {t.rows.length} rows
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          aria-label="Filter column"
          value={filterColumn}
          onChange={(e) => {
            setFilterColumn(e.target.value);
            setPage(0);
          }}
          style={inputStyle}
        >
          <option value="">Filter column…</option>
          {table.columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          aria-label="Filter text"
          value={filterText}
          onChange={(e) => {
            setFilterText(e.target.value);
            setPage(0);
          }}
          placeholder="contains…"
          style={{ ...inputStyle, width: 160 }}
        />
        <select
          aria-label="Sort column"
          value={sortColumn}
          onChange={(e) => setSortColumn(e.target.value)}
          style={inputStyle}
        >
          <option value="">Sort…</option>
          {table.columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <Button
          variant="secondary"
          onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
        >
          {sortDir === "asc" ? "Ascending" : "Descending"}
        </Button>
      </div>

      {gridFor(table, pageRows, `${file.name} rows`)}

      <div className="mt-2.5 flex items-center gap-3 text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
        <span>
          {shown.length} row{shown.length === 1 ? "" : "s"} · page {Math.min(page + 1, pageCount)} of {pageCount}
        </span>
        <span className="ml-auto flex gap-2">
          <Button variant="secondary" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
            Previous
          </Button>
          <Button
            variant="secondary"
            disabled={page + 1 >= pageCount}
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
          >
            Next
          </Button>
        </span>
      </div>

      {stats.length > 0 ? (
        <>
          <GroupLabel>Column stats · numeric</GroupLabel>
          <Group>
            {stats.map((s, i) => (
              <Row key={s.column} last={i === stats.length - 1}>
                <Lab>{s.column}</Lab>
                <Val>
                  min {s.min} · max {s.max} · avg {s.avg}
                </Val>
              </Row>
            ))}
          </Group>
        </>
      ) : null}

      <GroupLabel>SQL console</GroupLabel>
      <div
        className="p-3.5"
        style={{
          backgroundColor: "var(--wb-surface-2)",
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-lg)",
        }}
      >
        <Sub>
          SELECT … FROM {tables.map((t) => t.name).join(" | ")} — one statement; unknown tables or
          columns are refused, never guessed.
        </Sub>
        <textarea
          aria-label="SQL query"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          placeholder={`SELECT * FROM ${table.name} LIMIT 5`}
          rows={3}
          className="mt-2.5 w-full font-mono text-[13px]"
          style={{ ...inputStyle, resize: "vertical" }}
        />
        <div className="mt-2 flex items-center gap-3">
          <Button onClick={runSql} disabled={sqlBusy || !sql.trim()}>
            {sqlBusy ? "Running…" : "Run query"}
          </Button>
          {sqlResult?.ok ? (
            <span className="text-[13px]" style={{ color: "var(--wb-content-secondary)" }}>
              Answered by the {sqlResult.source === "engine" ? "dataset engine" : "served snapshot"}
            </span>
          ) : null}
        </div>
        {sqlResult ? (
          sqlResult.ok ? (
            <div className="mt-3">{gridFor(sqlResult.table, sqlResult.table.rows, "SQL result")}</div>
          ) : (
            <p role="alert" className="mt-3 mb-0 text-sm" style={{ color: "var(--wb-danger)" }}>
              {sqlResult.reason}
            </p>
          )
        ) : null}
      </div>
    </div>
  );
}
