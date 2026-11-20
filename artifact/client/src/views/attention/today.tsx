// Today — the original's renderToday(): the headline,
// the presence scope line, the summary strip, the glance
// card, the handler dots, and the banded item cards; and,
// when presence is Away, the ambient glance (storyboard
// frames 1, 2, and 6 — presentations of this one view).
//
// Reads ride portion(): glance and today load
// independently, last-good copies render flagged stale,
// and when neither has ever loaded the view says so
// plainly — "nothing is being hidden; this is the whole
// report" (the original's unreachable line, verbatim in
// substance). A portion that alone has never loaded
// says so in its own place, in the same line's form —
// the glance where its card would sit, the review
// bands where the bands would sit — never a silent
// absence beside the portion that did load.

import { useEffect, useRef } from "react";
import { Button } from "@workhorse/kit/components/Button";
import { Card } from "@workhorse/kit/components/Card";
import { DegradedBanner } from "@workhorse/kit/components/DegradedBanner";
import { EmptyState } from "@workhorse/kit/components/EmptyState";
import { ItemCard } from "./item-card";
import {
  clock,
  day,
  type GlancePayload,
  type PresenceView,
  type TodayPayload,
} from "./model";
import { postPresenceMode } from "./presence";
import { api, call, staleText, usePortion } from "./transport";
import { BandHead, PageColumn, PresenceDot, ScopeLine, SlotDot, ViewTitle, useAttentionUi } from "./ui";
import type { ViewProps } from "../../lib/view-contract";

export function TodayView({ onBadges }: Pick<ViewProps, "onBadges">) {
  const ui = useAttentionUi();
  const glance = usePortion<GlancePayload>("glance", () => call(api.getGlance({})), ui.refreshKey);
  const today = usePortion<TodayPayload>("today", () => call(api.getToday({})), ui.refreshKey);
  const bandsRef = useRef<HTMLDivElement | null>(null);

  const gl = glance.data;
  const td = today.data;
  const needs = td ? td.headline_count : gl ? gl.decision_count : 0;

  // The today badge feeds the shell (INTEGRATION.md §6:
  // the Launcher's decision count rides it).
  useEffect(() => {
    if (gl || td) onBadges({ today: { count: needs, hot: needs > 0 } });
  }, [gl, td, needs, onBadges]);

  if (!gl && !td) {
    return (
      <PageColumn>
        <ViewTitle>Today</ViewTitle>
        {glance.loading || today.loading ? (
          <ScopeLine>Loading…</ScopeLine>
        ) : (
          <EmptyState message="The surface is unreachable — nothing is being hidden; this is the whole report." />
        )}
      </PageColumn>
    );
  }

  const presence: PresenceView | null = gl ? gl.presence : td ? td.presence : null;

  if (gl && gl.presence.mode === "away") {
    return (
      <PageColumn>
        <AwayGlance gl={gl} td={td} />
      </PageColumn>
    );
  }

  const stale = glance.stale || today.stale;
  const bt = td?.bands.find((b) => b.band === "breakthrough");
  const due = td?.bands.find((b) => b.band === "due_today");
  const dec = td?.bands.find((b) => b.band === "needs_decision");
  const segs: { text: string; strong: boolean }[] = [];
  if (bt && bt.items.length) segs.push({ text: `${bt.items.length} breakthrough — Work it`, strong: true });
  if (due && due.items.length) segs.push({ text: `${due.items.length} due today — Review`, strong: false });
  if (dec && dec.items.length)
    segs.push({ text: `${dec.items.length} decision${dec.items.length > 1 ? "s" : ""} — Review`, strong: false });

  return (
    <PageColumn>
      <ViewTitle>{needs ? `${needs} decision${needs > 1 ? "s" : ""} waiting` : "Nothing needs you"}</ViewTitle>
      <ScopeLine>
        {presence ? (
          <>
            <PresenceDot mode={presence.mode} /> {presence.mode_label}
            {presence.expires_at ? ` · until ${clock(presence.expires_at)}` : ""}
            {" · "}
          </>
        ) : null}
        everything else is held or handled{staleText(stale)}
      </ScopeLine>

      {segs.length ? (
        <div
          className="mb-4 flex flex-wrap items-center gap-2 px-3.5 py-2.5 text-sm"
          style={{
            backgroundColor:
              bt && bt.items.length
                ? "color-mix(in srgb, var(--wb-okabe-orange) 16%, var(--wb-surface-2))"
                : "color-mix(in srgb, var(--wb-okabe-sky-blue) 14%, var(--wb-surface-2))",
            borderRadius: "var(--wb-radius-md)",
            color: "var(--wb-content-primary)",
          }}
        >
          <span>
            {segs.map((s, i) => (
              <span key={i}>
                {i > 0 ? " · " : ""}
                {s.text}
              </span>
            ))}
          </span>
          <Button
            variant="secondary"
            onClick={() => {
              // The original's Go (data-goto="bands"):
              // scroll to the bands — the review queue
              // below. The original's main scrolled the
              // window; in the one client the bands live
              // inside the AppShell's scrolling content
              // region, so scroll THAT region (the bands'
              // nearest scrollable ancestor) to the bands'
              // head — the same destination and flow.
              const el = bandsRef.current;
              if (!el) return;
              const reduce = window.matchMedia(
                "(prefers-reduced-motion: reduce)",
              ).matches;
              let scroller: HTMLElement | null = el.parentElement;
              while (scroller) {
                const oy = window.getComputedStyle(scroller).overflowY;
                if (
                  (oy === "auto" || oy === "scroll") &&
                  scroller.scrollHeight > scroller.clientHeight
                ) {
                  break;
                }
                scroller = scroller.parentElement;
              }
              if (!scroller) {
                el.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
                return;
              }
              const top =
                el.getBoundingClientRect().top -
                scroller.getBoundingClientRect().top +
                scroller.scrollTop;
              scroller.scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
            }}
          >
            Go
          </Button>
        </div>
      ) : null}

      {gl ? (
        <Card className="mb-2" title="Glance">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            <span className="text-[34px] font-bold">{clock(gl.clock.now)}</span>
            <span className="text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              Next digest {gl.clock.next_window_at ? day(gl.clock.next_window_at) : "—"}
            </span>
            <span className="text-sm">
              <b>{gl.breakthrough_count}</b> breakthrough
            </span>
            <span className="text-sm">
              <b>{gl.held_count}</b> of yours held
            </span>
          </div>
          {gl.next_due ? (
            <p className="mt-1.5 text-sm" style={{ color: "var(--wb-content-secondary)" }}>
              Next due — {gl.next_due.title} · {gl.next_due.handler_label} · {gl.next_due.due_label}
            </p>
          ) : null}
        </Card>
      ) : glance.error ? (
        <EmptyState
          className="mb-2"
          message="The glance is unreachable — nothing is being hidden; this is the whole report."
        />
      ) : null}

      {gl && gl.handler_dots.length ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {gl.handler_dots.map((d) => (
            <Button
              key={d.handle}
              variant="secondary"
              onClick={() => ui.navigate(`#/attention/handlers/${encodeURIComponent(d.handle)}`)}
            >
              <SlotDot slot={d.color_slot} /> {d.handle} · {d.needs_decision}
            </Button>
          ))}
        </div>
      ) : null}

      {td ? (
        <div ref={bandsRef} id="bands">
          {td.bands.map((band) => (
            <section key={band.band}>
              <BandHead label={band.band_label} count={band.items.length} />
              {band.unavailable ? (
                <DegradedBanner
                  message={`${band.unavailable.reason} — showing the last good copy from ${day(band.unavailable.last_good_at)}.`}
                />
              ) : band.items.length === 0 ? null : band.collapsed ? (
                <details>
                  <summary
                    className="mb-2 cursor-pointer text-sm"
                    style={{ color: "var(--wb-content-secondary)" }}
                  >
                    {band.items.length} item{band.items.length === 1 ? "" : "s"} — tap to open
                  </summary>
                  {band.items.map((it) => (
                    <ItemCard key={it.id} item={it} band={band.band} />
                  ))}
                </details>
              ) : (
                band.items.map((it) => <ItemCard key={it.id} item={it} band={band.band} />)
              )}
            </section>
          ))}
          {!td.bands.some((b) => b.items.length) && !td.held_total_count ? (
            <EmptyState message="Nothing is waiting — every thread is working or settled." />
          ) : null}
          {td.held_total_count ? (
            <ScopeLine>
              {td.held_owner_count} of yours and {td.held_total_count} in all held while{" "}
              {td.presence.mode_label}.
            </ScopeLine>
          ) : null}
        </div>
      ) : today.error ? (
        <EmptyState message="The review bands are unreachable — nothing is being hidden; this is the whole report." />
      ) : null}
    </PageColumn>
  );
}

/** The Away variant: the ambient glance (the original's
 *  away screen; storyboard frame 6 is its night state). */
function AwayGlance({ gl, td }: { gl: GlancePayload; td: TodayPayload | null }) {
  const ui = useAttentionUi();
  const heldOwner = td ? td.held_owner_count : gl.held_count;
  const heldTotal = td ? td.held_total_count : gl.held_count;
  const until = gl.presence.expires_at ? ` until ${clock(gl.presence.expires_at)}` : "";

  return (
    <>
      <Card title="Away glance">
        <div className="flex flex-col gap-2">
          <span className="text-[52px] leading-none font-extrabold">{clock(gl.clock.now)}</span>
          <span className="text-[15px]">
            You're away{until}.
          </span>
          <span className="flex flex-wrap items-center gap-2 text-[15px]">
            <span>
              <b>{gl.breakthrough_count}</b> breakthrough item
              {gl.breakthrough_count === 1 ? "" : "s"} can reach you
            </span>
            {gl.breakthrough_count ? (
              <Button
                variant="primary"
                onClick={async () => {
                  try {
                    await postPresenceMode("active", null);
                    ui.notify("Presence set — Active");
                    ui.refresh();
                  } catch (e) {
                    ui.notify(`Presence failed: ${e instanceof Error ? e.message : String(e)}`);
                  }
                }}
              >
                Review in Active
              </Button>
            ) : null}
          </span>
          {gl.breakthrough_items.map((i) => (
            <span key={i.title} className="text-[15px]">
              <b>{i.title}</b> · {i.handler_label}
            </span>
          ))}
          <span className="text-[15px]">
            <b>{heldOwner}</b> of yours · <b>{heldTotal}</b> in all held for your return
          </span>
          <span className="text-[15px]" style={{ color: "var(--wb-content-secondary)" }}>
            Next digest {gl.clock.next_window_at ? day(gl.clock.next_window_at) : "—"}
          </span>
          {gl.down_sources.length ? (
            <span className="text-[15px]" style={{ color: "var(--wb-content-secondary)" }}>
              Source down: {gl.down_sources.join(", ")} — its items may be missing from this
              picture.
            </span>
          ) : null}
        </div>
      </Card>
    </>
  );
}
