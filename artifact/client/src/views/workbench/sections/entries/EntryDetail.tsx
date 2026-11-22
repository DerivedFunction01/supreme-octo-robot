// Drill-in for one entry (Subplan 06 Step 2 + 3): the
// entry's page, which opens as a full page of the
// client from this sheet's door frame (FU-1, owner
// ruling 2026-11-16 — the embedded stage that rendered
// it here is retired), beside the recorded-state
// summary, metadata, lifecycle actions, files, review
// log and history. Every write
// goes through the server's entry action (lib/ mutation,
// actor=viewer); a refusal — ruling required, uniformity
// findings, version conflict — is surfaced with the
// server's own reason, never as a silent failure or a
// spinner. The viewer's own state controls retired with
// the byte route, and its review disposition retired with
// the hosted route: an entry's questions live in its page
// now, and answers are recorded by transcription in the
// owning thread (SPEC §5.1). Since the 2026-11-10
// unification this one drill-in serves every kind — the
// retired sibling detail for kind `artifact` composed
// the same cards over the same blocks, and its surfaces
// (stage, metadata, lifecycle, files, review log,
// history) all live here.
//
// Composition only (2026-11-05 follow-up split):
// useEntryDetail + Disposition. (The annotation /
// commenting machinery that used to compose here was
// removed 2026-11-17 on the owner's ruling — he does
// not use it; the backend records are untouched.)

import { Button } from "@workhorse/kit/components/controls/Button";
import { Frame } from "@workhorse/kit/components/shell/Frame";
import { useIsPhone } from "../../lib/responsive";
import { entryPageHref } from "../../lib/routing";
import { useDisposition } from "./Disposition";
import { FilePanel } from "./FilePanel";
import { HistoryList, ReviewLog } from "./HistoryLog";
import { EntryBadges, OwnerLine, PreviewSummary } from "./helpers";
import { LifecycleCard } from "./LifecycleCard";
import { MetaCard } from "./meta";
import type { FullEntry } from "./types";
import { useEntryDetail } from "./useEntryDetail";

export function EntryDetail({
  slug,
  entryId,
  feedEntry,
  onClose,
  onMutated,
}: {
  slug: string;
  entryId: string;
  feedEntry: FullEntry | null;
  onClose: () => void;
  onMutated: () => void;
}) {
  const isPhone = useIsPhone();

  const {
    detailQuery,
    detail,
    detailError,
    entry,
    derived,
    approval,
    needsChanges,
    supersedeCandidates,
    candidateLabel,
    supersededByTitle,
  } = useEntryDetail(slug, entryId, feedEntry);

  const disposition = useDisposition({ slug, entryId, entry, onMutated });
  const { actionError, actionNotice, runAction, busy } = disposition;

  if (detailQuery.isPending && !entry) {
    return (
      <section data-anchor="mockups/entry-sheet">
        <p style={{ color: "var(--wb-content-secondary)" }}>Loading {entryId}…</p>
      </section>
    );
  }
  if (!entry) {
    return (
      <section data-anchor="mockups/entry-sheet">
        <Button variant="ghost" onClick={onClose}>
          ← All entries
        </Button>
        <p role="alert" style={{ color: "var(--wb-danger)" }}>
          Entries: {detailError ?? `entry ${entryId} could not be loaded.`}
        </p>
      </section>
    );
  }

  return (
    <section data-anchor="mockups/entry-sheet">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--wb-space-12)",
          flexWrap: "wrap",
          marginBottom: "var(--wb-space-16)",
        }}
      >
        <Button variant="ghost" onClick={onClose}>
          ← All entries
        </Button>
        <h2
          style={{
            fontSize: "var(--wb-font-size-lg)",
            lineHeight: "var(--wb-line-height-lg)",
            fontWeight: 600,
            margin: 0,
          }}
        >
          {entry.title}
        </h2>
        <EntryBadges derived={derived} approval={approval} needsChanges={needsChanges} />
        <OwnerLine entry={entry} />
        {entry.archived ? (
          <span style={{ color: "var(--wb-content-secondary)" }}>Archived</span>
        ) : null}
      </div>

      {detailError ? (
        <p role="status" style={{ color: "var(--wb-content-secondary)" }}>
          Entry detail (history and files) could not be loaded — {detailError} What follows is the
          feed's record for this entry.
        </p>
      ) : null}
      {actionError ? (
        <p
          role="alert"
          style={{
            color: "var(--wb-danger)",
            border: "1px solid var(--wb-danger)",
            borderRadius: "var(--wb-radius-md)",
            padding: "var(--wb-space-12) var(--wb-space-16)",
          }}
        >
          {actionError}
        </p>
      ) : null}
      {actionNotice ? (
        <p role="status" style={{ color: "var(--wb-content-secondary)" }}>
          {actionNotice}
        </p>
      ) : null}

      <div
        style={{
          display: "grid",
          // Phone: one column — the stage first, then
          // the card column stacked under it. Phone:
          // minmax(0, 1fr), not 1fr — a bare 1fr is
          // minmax(auto, 1fr) and the stage's min-content
          // (frame header + summary) blows the track out to
          // 398px in a 358px column (measured on the
          // drill-in). Desktop's 7fr/5fr is untouched.
          gridTemplateColumns: isPhone ? "minmax(0, 1fr)" : "7fr 5fr",
          gap: "var(--wb-space-24)",
          alignItems: "start",
        }}
      >
        <div style={isPhone ? { minWidth: 0 } : { position: "sticky", top: "var(--wb-space-16)" }}>
          {/* The page's door (FU-1): its one action
              navigates to the entry's full-page preview
              route — the page no longer renders inside
              the drill-in. The frame is titled by its
              function, not the entry's name: the header
              line above already titles this drill-in
              with the entry's title, and the frame
              wearing it too was one of the three
              renderings of the title on this screen
              (critic M-5). A held-by-reference entry has
              no page to open and says so in the stage's
              own words. */}
          <Frame
            anchor="artifacts/exhibit-stage"
            title="Full page"
            viewportLabel={`${entry.source_kind} · rendered page`}
            archived={entry.archived}
          >
            {entry.source_kind === "entry-dir" && entry.main_file ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--wb-space-12)",
                  flexWrap: "wrap",
                }}
              >
                <Button
                  variant="primary"
                  onClick={() => {
                    window.location.hash = entryPageHref(slug, entry.id);
                  }}
                >
                  Open full page
                </Button>
                <span
                  className="mono"
                  style={{
                    color: "var(--wb-content-secondary)",
                    fontSize: "var(--wb-font-size-sm)",
                    // An unbroken path token wraps rather
                    // than squeezing the door's button —
                    // a button never truncates (owner
                    // ruling 2026-11-17); the same cure
                    // the recorded-state source_ref wears.
                    overflowWrap: "anywhere",
                  }}
                >
                  {entry.main_file}
                </span>
              </div>
            ) : (
              <p style={{ margin: 0, color: "var(--wb-content-secondary)" }}>
                Page unavailable — this item is held by reference; its files live outside the
                harness.
              </p>
            )}
          </Frame>
          {/* The recorded state, ungrouped (F5, ruling q3
              retitle-and-ungroup): the frame above is the
              page's door, not a preview of the entry. The
              recorded state is not a second preview either
              and does not wear its title or a frame of its
              own; it is a headed record under the door. */}
          <section aria-label="Recorded state" style={{ marginTop: "var(--wb-space-16)" }}>
            <h3
              style={{
                fontSize: "var(--wb-font-size-xs)",
                lineHeight: "var(--wb-line-height-xs)",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--wb-content-secondary)",
                margin: "0 0 var(--wb-space-8)",
              }}
            >
              Recorded state
            </h3>
            <PreviewSummary entry={entry} />
          </section>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--wb-space-16)",
            minWidth: isPhone ? 0 : undefined,
          }}
        >
          <MetaCard entry={entry} derived={derived} supersededByTitle={supersededByTitle} />

          <LifecycleCard
            entry={entry}
            derived={derived}
            busy={busy}
            runAction={runAction}
            statusChoice={disposition.statusChoice}
            setStatusChoice={disposition.setStatusChoice}
            ruling={disposition.ruling}
            setRuling={disposition.setRuling}
            gate={disposition.gate}
            setGate={disposition.setGate}
            acceptDrift={disposition.acceptDrift}
            setAcceptDrift={disposition.setAcceptDrift}
            supersedeTarget={disposition.supersedeTarget}
            setSupersedeTarget={disposition.setSupersedeTarget}
            supersedeCandidates={supersedeCandidates}
            candidateLabel={candidateLabel}
          />

          {detail ? (
            <>
              <div data-anchor="mockups/files-card">
                <FilePanel
                  slug={slug}
                  entryId={entryId}
                  files={detail.files}
                  configPath={entry.config_path ?? null}
                  onMutated={disposition.invalidate}
                />
              </div>
              <div data-anchor="mockups/review-log-card">
                <ReviewLog history={detail.history} />
              </div>
              <div data-anchor="mockups/history-card">
                <HistoryList history={detail.history} />
              </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
