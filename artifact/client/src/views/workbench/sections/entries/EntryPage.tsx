// One entry's page as a full page of the one client
// (FU-1, owner ruling: the
// workbench preview loads as a full page — a top bar
// with a go-back control and an info icon; the info
// icon opens a popup drawer on mobile and the desktop
// presentation on desktop). This route replaces the
// embedded stage inside the drill-in: the drill-in's
// frame is now the door, and opening it navigates here.
//
// The page itself renders exactly as the embedded stage
// rendered it — the behaviour of record the FU-1 census
// established, preserved byte for byte and sandbox for
// sandbox: the getEntryPage action fetches the entry's
// main file over the raw contract, and the bytes render
// as a document in a sandboxed srcDoc iframe
// (allow-scripts, opaque origin — the page cannot reach
// the client, the client cannot reach into the page;
// the runtime's own storage is best-effort inside the
// sandbox, as it was in the stage). Only the
// presentation changed: a box in the drill-in is now a
// page. The server-composed alternative was evaluated
// and refused on evidence (INTEGRATION.md §11.7): the
// companion server's loopback address resolves on the
// reader's own device, and the platform serves this one
// document from the client's own origin, where entry
// scripts must never run.
//
// Chrome: the bar is the kit's Button on --ui-* tokens
// and follows the shell's appearance state like every
// surface. The info surface is the kit's one Sheet —
// the popup drawer at phone width, the docked side
// panel on desktop — carrying the entry record's own
// fields in the drill-in metadata rows' form; nothing
// is invented for it.

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { kindLabel, ruledStatusLabel } from "../../lib/labels";
import { sectionHref } from "../../lib/routing";
import { navigate } from "../../../../lib/router";
import { MetaRow } from "./meta";
import type { EntriesFeedFull, EntryDetail, Envelope, FullEntry } from "./types";

interface PagePayload {
  contentType: string | null;
  bodyBase64: string;
  bytes: number;
}

/** Decode base64 to text the way the bytes arrived: the
 * byte route serves the file verbatim, so the decode is
 * byte-exact (atob to bytes, bytes as UTF-8) and the
 * page renders the text unmodified. (The stage's own
 * decode, carried verbatim.) */
function decodePage(bodyBase64: string): string {
  const binary = atob(bodyBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

/** The info glyph, drawn locally in the kit's icon
 * grammar (Lucide-style, currentColor) — the seam
 * INTEGRATION.md §11.1 leaves for surface glyphs. */
function InfoGlyph() {
  return (
    <svg
      width={19}
      height={19}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}

const schemaHeadingStyle: React.CSSProperties = {
  fontSize: "var(--ui-font-size-xs)",
  lineHeight: "var(--ui-line-height-xs)",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--ui-content-secondary)",
  margin: "var(--ui-space-16) 0 var(--ui-space-8)",
};

/** The record's state schema, summarised from the
 * record itself: each declared question with its type,
 * its options, its recommendation, and the recorded
 * current value where the record carries one. */
function SchemaSummary({ entry }: { entry: FullEntry }) {
  const schema = (entry.state_schema ?? {}) as Record<string, Record<string, unknown>>;
  const keys = Object.keys(schema);
  if (keys.length === 0) return null;
  return (
    <>
      <h3 style={schemaHeadingStyle}>State schema</h3>
      {keys.map((key) => {
        const spec = schema[key] ?? {};
        const question = typeof spec.question === "string" ? spec.question : key;
        const type = typeof spec.type === "string" ? spec.type : "value";
        const options = Array.isArray(spec.options) ? spec.options.map(String) : null;
        const recommended = typeof spec.recommended === "string" ? spec.recommended : null;
        const current = entry.state_json?.[key];
        return (
          <MetaRow key={key} label={key}>
            {question} — {type}
            {options ? ` · ${options.join(" / ")}` : ""}
            {recommended ? ` · recommended: ${recommended}` : ""}
            {current !== undefined ? ` · current: ${String(current)}` : ""}
          </MetaRow>
        );
      })}
    </>
  );
}

export function EntryPage({ slug, entryId }: { slug: string; entryId: string }) {
  const [infoOpen, setInfoOpen] = useState(false);

  // The entry record — the same detail query the
  // drill-in runs (shared cache entry), so arriving
  // from the drill-in is warm.
  const detailQuery = useQuery({
    queryKey: ["entry", slug, entryId],
    queryFn: () => api.getEntry({ slug, entryId }),
  });
  const detailEnvelope = detailQuery.data as Envelope | undefined;
  const detail =
    detailEnvelope && detailEnvelope.status === 200
      ? (detailEnvelope.payload as EntryDetail)
      : null;
  const entry: FullEntry | null = detail?.entry ?? null;
  const detailError = detailQuery.isError
    ? "The entry could not be fetched — the action did not reach the server."
    : detailEnvelope && detailEnvelope.status !== 200
      ? (detailEnvelope.error ?? "the entry could not be loaded.")
      : null;

  // The project's display name, from the same feed
  // query the section list runs (shared cache entry).
  const feedQuery = useQuery({
    queryKey: ["entries", slug, false],
    queryFn: () => api.getEntries({ slug }),
  });
  const feedEnvelope = feedQuery.data as Envelope | undefined;
  const feed =
    feedEnvelope && feedEnvelope.status === 200 && feedEnvelope.payload
      ? (feedEnvelope.payload as EntriesFeedFull)
      : null;
  const projectName = feed?.name ?? slug;

  // The page bytes — the stage's own query, keyed on
  // the entry's recorded fingerprint, so a rebuilt page
  // renders its new bytes on the next open.
  const mainFile = entry?.source_kind === "entry-dir" ? entry.main_file : null;
  const pageQuery = useQuery({
    queryKey: ["entry-page", slug, entry?.id, entry?.content_sha256],
    queryFn: () => api.getEntryPage({ slug, entryId: entry!.id }),
    enabled: entry != null && mainFile != null,
  });
  const pageEnvelope = pageQuery.data;
  const pagePayload =
    pageEnvelope && pageEnvelope.status === 200
      ? (pageEnvelope.payload as PagePayload | null)
      : null;
  const pageText = useMemo(
    () => (pagePayload ? decodePage(pagePayload.bodyBase64) : null),
    [pagePayload],
  );
  const pageError = pageQuery.isError
    ? "The page could not be fetched — the action did not reach the server. Nothing was rendered."
    : pageEnvelope && pageEnvelope.status !== 200
      ? (pageEnvelope.error ?? `The byte route refused this page (status ${pageEnvelope.status}).`)
      : null;

  const goBack = () => {
    navigate(sectionHref(slug, "entries", entryId));
  };

  return (
    <div
      data-anchor="artifacts/exhibit-page"
      style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--ui-space-12)",
          padding: "var(--ui-space-8) var(--ui-space-12)",
          borderBottom: "1px solid var(--ui-border-default)",
          backgroundColor: "var(--ui-surface-1)",
          flex: "0 0 auto",
        }}
      >
        {/* The back control never shrinks: at phone
            width the title (next) flexes and truncates
            before the Back label does (critic WB5-2). */}
        <Button variant="ghost" className="shrink-0" onClick={goBack}>
          ← Back
        </Button>
        {/* The bar's title is title TEXT, not a heading:
            the shell provides the route's one H1 naming
            the section (the F2 one-H1 contract), and this
            bar's ruled chrome is its look — back control,
            the entry's title, the info action — not the
            element it is carried on. */}
        <div
          style={{
            fontSize: "var(--ui-font-size-lg)",
            lineHeight: "var(--ui-line-height-lg)",
            fontWeight: 600,
            margin: 0,
            flex: "1 1 auto",
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {entry?.title ?? entryId}
        </div>
        {entry?.archived ? (
          <span style={{ color: "var(--ui-content-secondary)", flex: "0 0 auto" }}>Archived</span>
        ) : null}
        <span style={{ marginLeft: "auto", display: "flex", flex: "0 0 auto" }}>
          <Button
            variant="ghost"
            iconOnly
            ariaLabel={`Information about ${entry?.title ?? entryId}`}
            disabled={entry == null}
            onClick={() => setInfoOpen(true)}
          >
            <InfoGlyph />
          </Button>
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        {detailQuery.isPending && !entry ? (
          <p
            style={{
              margin: 0,
              padding: "var(--ui-space-16)",
              color: "var(--ui-content-secondary)",
            }}
          >
            Loading entry…
          </p>
        ) : detailError && !entry ? (
          <p
            role="alert"
            style={{ margin: 0, padding: "var(--ui-space-16)", color: "var(--ui-danger)" }}
          >
            {detailError}
          </p>
        ) : entry && mainFile == null ? (
          <p
            style={{
              margin: 0,
              padding: "var(--ui-space-16)",
              color: "var(--ui-content-secondary)",
            }}
          >
            Page unavailable — this item is held by reference; its files live outside the harness.
          </p>
        ) : pageQuery.isPending ? (
          <p
            style={{
              margin: 0,
              padding: "var(--ui-space-16)",
              color: "var(--ui-content-secondary)",
            }}
          >
            Loading page…
          </p>
        ) : pageError ? (
          <p
            role="alert"
            style={{ margin: 0, padding: "var(--ui-space-16)", color: "var(--ui-danger)" }}
          >
            {pageError}
          </p>
        ) : pageText != null ? (
          <iframe
            title={`Rendered page of ${entry?.title ?? entryId}`}
            sandbox="allow-scripts"
            srcDoc={pageText}
            style={{
              display: "block",
              flex: 1,
              minHeight: 0,
              width: "100%",
              border: "none",
              background: "var(--ui-surface-1)",
            }}
          />
        ) : null}
      </div>

      {entry ? (
        <Sheet
          open={infoOpen}
          title={entry.title}
          onClose={() => setInfoOpen(false)}
          anchor="artifacts/exhibit-info"
        >
          <MetaRow label="Project">{projectName}</MetaRow>
          <MetaRow label="Kind">{kindLabel(entry.kind)}</MetaRow>
          <MetaRow label="Status">
            {ruledStatusLabel(entry.status)}
            {entry.gate ? ` · gate: ${entry.gate}` : ""}
          </MetaRow>
          <MetaRow label="Main file">
            <span className="mono">{entry.main_file ?? "—"}</span>
          </MetaRow>
          <MetaRow label="Version">
            <span className="num">{entry.version}</span>
          </MetaRow>
          <MetaRow label="Updated">
            {formatDate(entry.updated_at)} · status changed {formatDate(entry.status_changed_at)}
          </MetaRow>
          <SchemaSummary entry={entry} />
        </Sheet>
      ) : null}
    </div>
  );
}
