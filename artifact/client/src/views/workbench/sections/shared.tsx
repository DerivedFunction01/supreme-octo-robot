// Shared section frame pieces. A section is a frame with a
// truthful state: loading skeleton, server error (named, with
// the recovery, once), degraded banner, not-set-up state, or
// content. Empty states are content, not errors (ui-context):
// a sunken well, one line. No fabricated data anywhere — a
// section with nothing to show says so in its own words.

import type { ReactNode } from "react";
import type { FeedEnvelope } from "../lib/api-types";

const wellStyle: React.CSSProperties = {
  background: "var(--wb-surface-sunken)",
  border: "1px solid var(--wb-border-default)",
  borderRadius: "var(--wb-radius-lg)",
  padding: "var(--wb-panel-padding)",
  color: "var(--wb-content-secondary)",
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
};

export function EmptyWell({ children }: { children: ReactNode }) {
  return <div style={wellStyle}>{children}</div>;
}

export function ErrorWell({ section, message }: { section: string; message: string }) {
  return (
    <div style={{ ...wellStyle, color: "var(--wb-danger)" }} role="alert">
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
        background: "var(--wb-surface-1)",
        border: "1px solid var(--wb-border-strong)",
        borderRadius: "var(--wb-radius-md)",
        padding: "var(--wb-space-12) var(--wb-space-16)",
        color: "var(--wb-content-secondary)",
        fontSize: "var(--wb-font-size-sm)",
        lineHeight: "var(--wb-line-height-sm)",
        marginBottom: "var(--wb-space-16)",
      }}
      role="status"
    >
      {text}
    </div>
  );
}

export const sectionTitleStyle: React.CSSProperties = {
  fontSize: "var(--wb-font-size-xl)",
  lineHeight: "var(--wb-line-height-xl)",
  fontWeight: 600,
  letterSpacing: "-0.011em",
  margin: "0 0 var(--wb-space-16)",
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
  gap: "var(--wb-space-12)",
  minHeight: "var(--wb-row-height)",
  padding: "var(--wb-space-8) var(--wb-space-12)",
  borderBottom: "1px solid var(--wb-border-default)",
  color: "var(--wb-content-primary)",
  textDecoration: "none",
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
};

export const metaStyle: React.CSSProperties = {
  color: "var(--wb-content-muted)",
  fontSize: "var(--wb-font-size-xs)",
  lineHeight: "var(--wb-line-height-xs)",
  whiteSpace: "nowrap",
};

export const badgeStyle: React.CSSProperties = {
  background: "var(--wb-surface-sunken)",
  borderRadius: "var(--wb-radius-pill)",
  padding: "0 var(--wb-space-8)",
  fontSize: "var(--wb-font-size-xs)",
  lineHeight: "var(--wb-line-height-xs)",
  color: "var(--wb-content-secondary)",
};
