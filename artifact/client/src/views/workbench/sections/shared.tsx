// Shared section frame pieces. A section is a frame with a
// truthful state: loading skeleton, server error (named, with
// the recovery, once), degraded banner, not-set-up state, or
// content. Empty states are content, not errors (ui-context):
// a sunken well, one line. No fabricated data anywhere — a
// section with nothing to show says so in its own words.

import type { ReactNode } from "react";
import type { FeedEnvelope } from "../lib/api-types";

const wellStyle: React.CSSProperties = {
  background: "var(--ui-surface-sunken)",
  border: "1px solid var(--ui-border-default)",
  borderRadius: "var(--ui-radius-lg)",
  padding: "var(--ui-panel-padding)",
  color: "var(--ui-content-secondary)",
  fontSize: "var(--ui-font-size-sm)",
  lineHeight: "var(--ui-line-height-sm)",
};

export function EmptyWell({ children }: { children: ReactNode }) {
  return <div style={wellStyle}>{children}</div>;
}

export function ErrorWell({ section, message }: { section: string; message: string }) {
  return (
    <div style={{ ...wellStyle, color: "var(--ui-danger)" }} role="alert">
      {section}: {message}
    </div>
  );
}

export function SkeletonWell({ label }: { label: string }) {
  return (
    <div style={wellStyle} aria-busy="true">
      Loading {label}…
    </div>
  );
}

export function DegradedBanner({ feed }: { feed: FeedEnvelope }) {
  if (!feed.degraded && feed.available) return null;
  const text = feed.degraded
    ? `This project's data is degraded${feed.reason ? ` — ${feed.reason}` : ""}.`
    : `This section is not set up for this project${feed.reason ? ` — ${feed.reason}` : ""}.`;
  return (
    <div
      style={{
        background: "var(--ui-surface-1)",
        border: "1px solid var(--ui-border-strong)",
        borderRadius: "var(--ui-radius-md)",
        padding: "var(--ui-space-12) var(--ui-space-16)",
        color: "var(--ui-content-secondary)",
        fontSize: "var(--ui-font-size-sm)",
        lineHeight: "var(--ui-line-height-sm)",
        marginBottom: "var(--ui-space-16)",
      }}
      role="status"
    >
      {text}
    </div>
  );
}

export const sectionTitleStyle: React.CSSProperties = {
  fontSize: "var(--ui-font-size-xl)",
  lineHeight: "var(--ui-line-height-xl)",
  fontWeight: 600,
  letterSpacing: "-0.011em",
  margin: "0 0 var(--ui-space-16)",
};

/** A detail title — styled title TEXT, never a heading
 * element, and never the SECTION's name: the shell
 * provides the route's one H1 naming the section
 * (App.tsx, the F2 one-H1 contract), and a view that
 * also rendered the section name as a big visual title
 * stacked a second visible title under the H1 (critic
 * M-5; the F4 demotion to this div cured the DOM half,
 * the re-run measured the visible stack remaining).
 * This component is for titles that name the ITEM in
 * view — a repo's display name in its detail header —
 * which the H1 does not carry. */
export function SectionTitle({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return <div style={{ ...sectionTitleStyle, ...style }}>{children}</div>;
}

export const listRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--ui-space-12)",
  minHeight: "var(--ui-row-height)",
  padding: "var(--ui-space-8) var(--ui-space-12)",
  borderBottom: "1px solid var(--ui-border-default)",
  color: "var(--ui-content-primary)",
  textDecoration: "none",
  fontSize: "var(--ui-font-size-sm)",
  lineHeight: "var(--ui-line-height-sm)",
};

export const metaStyle: React.CSSProperties = {
  color: "var(--ui-content-muted)",
  fontSize: "var(--ui-font-size-xs)",
  lineHeight: "var(--ui-line-height-xs)",
  whiteSpace: "nowrap",
};

export const badgeStyle: React.CSSProperties = {
  background: "var(--ui-surface-sunken)",
  borderRadius: "var(--ui-radius-pill)",
  padding: "0 var(--ui-space-8)",
  fontSize: "var(--ui-font-size-xs)",
  lineHeight: "var(--ui-line-height-xs)",
  color: "var(--ui-content-secondary)",
};
