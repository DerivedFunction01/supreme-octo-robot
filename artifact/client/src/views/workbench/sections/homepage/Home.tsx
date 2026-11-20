// Workspace home (#/, repo-home spec §4): one row per
// swept project — identity/branch/HEAD, plan counts by
// bucket + the in-progress plan, todo counts, triage/stale
// counts, feed health — sorted by the server (in-progress
// first, then recent activity, then name).
//
// Worktrees are GROUPED (§19): the project row is the
// repo (its main checkout); linked worktrees nest under
// it as children, and only when the repo HAS them — a
// worktree strip never renders as an empty shell.

import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { HomePayload, HomeRow } from "../../lib/api-types";
import { formatDate, formatRelative } from "../../lib/format";
import { homeKey } from "../../lib/keys";
import { planBucketLabel, todoStatusLabel } from "../../lib/labels";
import { useIsPhone } from "../../lib/responsive";
import { sectionHref } from "../../lib/routing";
import { ActivePlanLine, WorktreeChildren } from "../board/worktreeViews";
import { EmptyWell, ErrorWell, metaStyle, SkeletonWell } from "../shared";
import { UpdatedAgo } from "../UpdatedAgo";

/** Outline count badge (derived values only — the
 * mockup's Home form carries the row's counts as badges). */
const countBadgeStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  // Spacing between the badge's label, count and suffix
  // rides the flex gap, never whitespace text nodes:
  // inside a flex container those collapse, which jammed
  // label+count together ("Plans2· 1 in progress",
  // critic m-6). Badge children are separate elements.
  gap: "var(--wb-space-4)",
  padding: "1px var(--wb-space-8)",
  border: "1px solid var(--wb-border-default)",
  borderRadius: "var(--wb-radius-pill)",
  fontSize: "var(--wb-font-size-xs)",
  lineHeight: "var(--wb-line-height-xs)",
  color: "var(--wb-content-secondary)",
  whiteSpace: "nowrap",
};

function countsLine(
  counts: Record<string, number>,
  order: string[],
  label: (raw: string) => string,
): string {
  return order
    .filter((key) => (counts[key] ?? 0) > 0)
    .map((key) => `${counts[key]} ${label(key).toLowerCase()}`)
    .join(" · ");
}

/** The slug fold's surface: stale standalone copies of
 * this project folded into its row by the sweep. One
 * muted line; the paths ride the title for the curious,
 * never a second peer card. */
function AlsoAtLine({ row }: { row: HomeRow }) {
  const also = row.also_at ?? [];
  if (also.length === 0) return null;
  return (
    <div style={{ ...metaStyle, marginTop: "var(--wb-space-4)" }} title={also.join("\n")}>
      <span className="num">{also.length}</span> {also.length === 1 ? "stale copy" : "stale copies"}{" "}
      folded into this project
    </div>
  );
}

function ProjectRow({ row }: { row: HomeRow }) {
  const isPhone = useIsPhone();
  const planCounts = countsLine(row.plans.counts, ["doing", "todo", "done"], planBucketLabel);
  const todoCounts = countsLine(
    row.todos.counts,
    ["doing", "blocked", "todo", "done"],
    todoStatusLabel,
  );
  if (isPhone) {
    // Phone form (mobile mockup, Exhibit 1): the project is
    // a card — the Home list is the project switcher (◆3).
    // Identity stacked (name, slug), the git line as badges
    // (branch badge + head + "main checkout" on a group
    // head), counts as count badges, then the same active
    // plan line and §19 nested worktrees as desktop.
    const children = row.worktrees.filter((w) => !w.is_main);
    return (
      <li
        style={{
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-lg)",
          background: "var(--wb-surface-1)",
          padding: "var(--wb-card-padding)",
          marginBottom: "var(--wb-space-16)",
        }}
      >
        <div>
          <a
            href={sectionHref(row.slug, "overview")}
            style={{
              color: "var(--wb-content-primary)",
              textDecoration: "none",
              fontWeight: 700,
              fontSize: "var(--wb-font-size-base)",
              lineHeight: "var(--wb-line-height-base)",
              // The name is the card's only target. As a
              // plain inline box its target height is the
              // font's content height (20px at base size);
              // the block box makes the base line-height
              // the target height — 24px (critic N-3).
              display: "inline-block",
            }}
          >
            {row.name}
          </a>
          <div className="mono" style={{ ...metaStyle, whiteSpace: "normal" }}>
            {row.slug}
          </div>
        </div>
        {row.git ? (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--wb-space-8)",
              alignItems: "center",
              marginTop: "var(--wb-space-8)",
            }}
          >
            <span className="mono" style={countBadgeStyle}>
              {row.git.branch ?? "detached"}
            </span>
            {row.git.head_short ? (
              <span className="mono" style={metaStyle}>
                {row.git.head_short}
              </span>
            ) : null}
            {children.length > 0 ? <span style={countBadgeStyle}>main checkout</span> : null}
          </div>
        ) : (
          <div style={{ ...metaStyle, marginTop: "var(--wb-space-8)" }}>not a git repo</div>
        )}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--wb-space-8)",
            marginTop: "var(--wb-space-8)",
          }}
        >
          {row.plans.available ? (
            <span style={countBadgeStyle}>
              <span>Plans</span>
              <span className="num">{row.plans.total}</span>
              {planCounts ? <span>· {planCounts}</span> : null}
            </span>
          ) : (
            <span style={countBadgeStyle}>No plans directory</span>
          )}
          {row.todos.available ? (
            <span style={countBadgeStyle}>
              <span>Todos</span>
              <span className="num">{row.todos.total}</span>
              {todoCounts ? <span>· {todoCounts}</span> : null}
            </span>
          ) : null}
          {row.review.available && row.review.triage_count > 0 ? (
            <span style={countBadgeStyle}>
              <span>Triage</span>
              <span className="num">{row.review.triage_count}</span>
            </span>
          ) : null}
          {row.review.available && row.review.stale_count > 0 ? (
            <span style={countBadgeStyle}>
              <span>Stale</span>
              <span className="num">{row.review.stale_count}</span>
            </span>
          ) : null}
        </div>
        {row.last_activity ? (
          <div style={{ ...metaStyle, marginTop: "var(--wb-space-8)" }}>
            active {formatDate(row.last_activity)} {formatRelative(row.last_activity)}
          </div>
        ) : null}
        {row.degraded ? (
          <div style={{ ...metaStyle, color: "var(--wb-danger)", marginTop: "var(--wb-space-4)" }}>
            degraded{row.reasons[0] ? ` — ${row.reasons[0]}` : ""}
          </div>
        ) : null}
        <AlsoAtLine row={row} />
        <div style={{ marginTop: "var(--wb-space-8)" }}>
          {row.showcase && row.showcase.source !== "none" ? (
            <ActivePlanLine slug={row.slug} active={row.showcase} />
          ) : row.plans.in_progress ? (
            <span style={{ display: "inline-flex", gap: "var(--wb-space-8)", flexWrap: "wrap" }}>
              <a
                href={sectionHref(row.slug, "plans", row.plans.in_progress.path)}
                style={{ color: "var(--wb-accent)", textDecoration: "none" }}
              >
                {row.plans.in_progress.title}
              </a>
              <span style={metaStyle}>{planBucketLabel("doing")}</span>
            </span>
          ) : (
            <span style={metaStyle}>No active plan</span>
          )}
        </div>
        <WorktreeChildren slug={row.slug} worktrees={row.worktrees} />
      </li>
    );
  }
  return (
    <li
      style={{
        borderBottom: "1px solid var(--wb-border-default)",
        padding: "var(--wb-space-12) 0",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--wb-space-12)",
          flexWrap: "wrap",
        }}
      >
        <a
          href={sectionHref(row.slug, "overview")}
          style={{
            color: "var(--wb-content-primary)",
            textDecoration: "none",
            fontWeight: 600,
          }}
        >
          {row.name}
        </a>
        <span className="mono" style={metaStyle}>
          {row.slug}
        </span>
        {row.git ? (
          <span style={metaStyle}>
            <span className="mono">{row.git.branch ?? "detached"}</span>
            {row.git.head_short ? (
              <>
                {" · "}
                <span className="mono">{row.git.head_short}</span>
              </>
            ) : null}
          </span>
        ) : (
          <span style={metaStyle}>not a git repo</span>
        )}
        {row.last_activity ? (
          <span style={metaStyle}>
            active {formatDate(row.last_activity)} {formatRelative(row.last_activity)}
          </span>
        ) : null}
        {row.degraded ? (
          <span style={{ ...metaStyle, color: "var(--wb-danger)" }}>
            degraded{row.reasons[0] ? ` — ${row.reasons[0]}` : ""}
          </span>
        ) : null}
      </div>
      <AlsoAtLine row={row} />
      <div
        style={{
          display: "flex",
          gap: "var(--wb-space-24)",
          flexWrap: "wrap",
          marginTop: "var(--wb-space-4)",
          fontSize: "var(--wb-font-size-sm)",
        }}
      >
        <span style={{ color: "var(--wb-content-secondary)" }}>
          {row.plans.available ? (
            <>
              Plans <span className="num">{row.plans.total}</span>
              {planCounts ? ` · ${planCounts}` : ""}
            </>
          ) : (
            "No plans directory"
          )}
        </span>
        <span style={{ color: "var(--wb-content-secondary)" }}>
          {row.todos.available ? (
            <>
              Todos <span className="num">{row.todos.total}</span>
              {todoCounts ? ` · ${todoCounts}` : ""}
            </>
          ) : (
            "No todos"
          )}
        </span>
        {row.review.available && (row.review.triage_count > 0 || row.review.stale_count > 0) ? (
          <span style={{ color: "var(--wb-content-secondary)" }}>
            <span className="num">{row.review.triage_count}</span> in triage ·{" "}
            <span className="num">{row.review.stale_count}</span> stale
          </span>
        ) : null}
      </div>
      <div style={{ marginTop: "var(--wb-space-4)" }}>
        {row.showcase && row.showcase.source !== "none" ? (
          <ActivePlanLine slug={row.slug} active={row.showcase} />
        ) : row.plans.in_progress ? (
          <span style={{ display: "inline-flex", gap: "var(--wb-space-8)" }}>
            <a
              href={sectionHref(row.slug, "plans", row.plans.in_progress.path)}
              style={{ color: "var(--wb-accent)", textDecoration: "none" }}
            >
              {row.plans.in_progress.title}
            </a>
            <span style={metaStyle}>{planBucketLabel("doing")}</span>
          </span>
        ) : (
          <span style={metaStyle}>No active plan</span>
        )}
      </div>
      {/* §19 grouping: linked worktrees nest under the repo
          row; nothing renders when there are none. */}
      <WorktreeChildren slug={row.slug} worktrees={row.worktrees} />
    </li>
  );
}

/** The Projects chooser (route #/projects): the Project
 * tab's destination when no project is in scope — the
 * same Home rows as a picker list. It never auto-selects
 * a project: the reader picks, and each row links to that
 * project's Overview. */
export function ProjectPickerSection() {
  return <HomeSection picker />;
}

export function HomeSection({ picker = false }: { picker?: boolean } = {}) {
  const isPhone = useIsPhone();
  const query = useQuery({
    queryKey: homeKey,
    queryFn: () => api.getHome({}),
    refetchInterval: 30000,
  });
  if (query.isPending) return <SkeletonWell label="the workspace home" />;
  if (query.isError || !query.data.payload) {
    return (
      <ErrorWell
        section="Home"
        message={query.data?.error ?? "the companion server did not answer."}
      />
    );
  }
  const feed = query.data.payload as unknown as HomePayload;
  const sweepErrors = (feed.sweep_errors ?? []) as { path?: string; reason?: string }[];
  return (
    <section data-anchor={picker ? "home/project-picker" : "home/project-list"}>
      {/* The shell's H1 names this route ("Projects");
          the view's own title line repeated it and
          stacked under the H1 (critic M-5, re-run). */}
      {isPhone ? (
        // The mockup's Home body opens with the section
        // label + project count (the top bar already
        // titles the view "Workbench"). On the Projects
        // route the phone chrome's large title already
        // names the surface "Projects", so the label is
        // dropped there — the same name twice in the
        // title block was critic M-5's phone finding.
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--wb-space-12)",
          }}
        >
          {picker ? (
            <span />
          ) : (
            <span
              style={{
                fontSize: "var(--wb-font-size-xs)",
                lineHeight: "var(--wb-line-height-xs)",
                fontWeight: 700,
                letterSpacing: "0.07em",
                textTransform: "uppercase",
                color: "var(--wb-content-muted)",
              }}
            >
              Projects
            </span>
          )}
          <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--wb-space-8)" }}>
            <UpdatedAgo capturedAt={feed.captured_at} />
            <span className="num" style={countBadgeStyle}>
              {feed.projects.length}
            </span>
          </span>
        </div>
      ) : picker ? null : (
        // The shell's H1 names this section ("Home");
        // the view carries no title line of its own —
        // a second visible title under the H1 was the
        // stacked-duplicate defect (critic M-5, re-run).
        // What stays on the header line is the sweep's
        // freshness stamp.
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "var(--wb-space-12)",
            marginBottom: "var(--wb-space-16)",
          }}
        >
          <UpdatedAgo capturedAt={feed.captured_at} />
        </div>
      )}
      {sweepErrors.length > 0 ? (
        <p style={{ color: "var(--wb-danger)" }}>
          {sweepErrors.map((e) => `${e.path ?? "sweep"}: ${e.reason ?? ""}`).join(" · ")}
        </p>
      ) : null}
      {feed.projects.length === 0 ? (
        <EmptyWell>
          No projects in the sweep.
        </EmptyWell>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {feed.projects.map((row) => (
            <ProjectRow key={`${row.slug}:${row.root}`} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}
