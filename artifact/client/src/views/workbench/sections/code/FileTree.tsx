// The Files tab's tree (absorption plan, step 8; made
// lazy by the datasets-release follow-ups): listings are
// served ONE directory at a time (files?dir=) — the tree
// fetches a folder's listing only when the folder is
// first expanded, and listings stay cached per directory
// for the life of the tab. Entries arrive classified
// tracked / untracked / ignored by git itself; the tree
// only arranges what was served and never re-derives a
// classification. Building the tree directory-first is
// what lets a huge repo browse at all: no whole-tree
// enumeration is ever capped away underneath it.
//
// Visibility: one toggle, the reference viewer's —
// "Show hidden & ignored" (default off). Hidden means
// any path segment is a dot-name (the served flag). With
// the toggle off, ignored and hidden files drop out of
// each loaded listing, hidden folders drop out, and a
// folder whose LOADED listing filters to empty drops
// out too; a folder not yet loaded always shows (its
// contents are unknown). Pruned folders (collapsed) are
// never expandable and never fetched.

import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Toggle } from "@workhorse/kit/components/controls/Toggle";
import { api } from "../../lib/api";
import type { RepoDirListing, RepoTreeFolder } from "../../lib/api-types-code";
import { metaStyle } from "../shared";
import { useCheckout } from "./checkoutContext";

function dirQueryKey(projectId: string, checkout: string | undefined, dir: string) {
  return ["code-dir", projectId, checkout, dir] as const;
}

/** One directory's listing query. Fetching is driven by
 * `enabled` (expansion); with staleTime Infinity a loaded
 * listing is served from cache for the life of the tab. */
function useDirListing(projectId: string, dir: string, enabled: boolean) {
  const checkout = useCheckout();
  return useQuery({
    queryKey: dirQueryKey(projectId, checkout, dir),
    queryFn: () => api.getCodeFiles({ projectId, checkout, dir }),
    enabled,
    staleTime: Infinity,
  });
}

type DirQuery = ReturnType<typeof useDirListing>;

function listingOf(query: DirQuery): RepoDirListing | null {
  const env = query.data;
  return env && env.status === 200 ? (env.payload as unknown as RepoDirListing) : null;
}

function errorOf(query: DirQuery): string | null {
  if (query.isError) return "the listing could not be loaded.";
  const env = query.data;
  if (env && env.status !== 200) return env.error ?? "the listing could not be loaded.";
  return null;
}

/** Whether a loaded listing still has anything to show
 * under the visibility filter. Descendant folders count
 * through their own listings when those are loaded
 * (read from the query cache); an unloaded folder counts
 * as content — it shows, per the toggle semantics. */
function listingHasVisibleContent(
  listing: RepoDirListing,
  queryClient: QueryClient,
  projectId: string,
  showAll: boolean,
  checkout?: string,
): boolean {
  for (const entry of listing.entries) {
    if (showAll || (entry.kind !== "ignored" && !entry.hidden)) return true;
  }
  for (const folder of listing.folders) {
    if (!showAll && folder.hidden) continue;
    if (folder.collapsed) return true;
    const env = queryClient.getQueryData<{ status: number; payload: unknown }>(
      dirQueryKey(projectId, checkout, folder.path),
    );
    const sub = env && env.status === 200 ? (env.payload as unknown as RepoDirListing) : null;
    if (!sub) return true;
    if (listingHasVisibleContent(sub, queryClient, projectId, showAll, checkout)) return true;
  }
  return false;
}

const kindMark: Record<string, string> = {
  untracked: "untracked",
  ignored: "ignored",
};

function baseName(path: string): string {
  return path.split("/").pop() ?? path;
}

function rowIndent(depth: number): React.CSSProperties {
  return {
    paddingLeft: `calc(var(--ui-space-12) + ${depth} * var(--ui-space-16))`,
  };
}

/** The rows of one loaded listing: folders first, then
 * files, each alphabetical — plus the cap notice under
 * the rows when this directory's listing truncated. */
function DirLevel({
  projectId,
  listing,
  depth,
  showAll,
  selected,
  onSelect,
  expanded,
  onToggle,
}: {
  projectId: string;
  listing: RepoDirListing;
  depth: number;
  showAll: boolean;
  selected: string | null;
  onSelect: (path: string) => void;
  expanded: Set<string>;
  onToggle: (path: string) => void;
}) {
  const folders = [...listing.folders].sort((a, b) =>
    baseName(a.path).localeCompare(baseName(b.path)),
  );
  const files = listing.entries.filter(
    (entry) => showAll || (entry.kind !== "ignored" && !entry.hidden),
  );
  return (
    <>
      {folders.map((folder) => (
        <FolderItem
          key={folder.path}
          projectId={projectId}
          folder={folder}
          depth={depth}
          showAll={showAll}
          selected={selected}
          onSelect={onSelect}
          expanded={expanded}
          onToggle={onToggle}
        />
      ))}
      {files.map((entry) => {
        const isSelected = selected === entry.path;
        return (
          <li key={entry.path}>
            <button
              type="button"
              aria-current={isSelected ? "true" : undefined}
              onClick={() => onSelect(entry.path)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--ui-space-8)",
                width: "100%",
                minHeight: "32px",
                textAlign: "left",
                paddingTop: "var(--ui-space-4)",
                paddingBottom: "var(--ui-space-4)",
                paddingRight: "var(--ui-space-8)",
                ...rowIndent(depth),
                paddingLeft: `calc(var(--ui-space-12) + ${depth} * var(--ui-space-16) + 38px)`,
                background: isSelected ? "var(--ui-surface-1)" : "transparent",
                border: "none",
                borderLeft: isSelected ? "2px solid var(--ui-accent)" : "2px solid transparent",
                color: "var(--ui-content-primary)",
                cursor: "pointer",
                fontFamily: "var(--ui-font-ui)",
              }}
            >
              <span
                className="mono"
                style={{ fontSize: "var(--ui-font-size-sm)", overflowWrap: "anywhere" }}
              >
                {baseName(entry.path)}
              </span>
              {entry.kind && kindMark[entry.kind] ? (
                <span style={metaStyle}>{kindMark[entry.kind]}</span>
              ) : null}
              {entry.hidden ? <span style={metaStyle}>hidden</span> : null}
            </button>
          </li>
        );
      })}
      {listing.truncated ? (
        <li>
          <p
            style={{
              ...metaStyle,
              whiteSpace: "normal",
              paddingTop: "var(--ui-space-4)",
              paddingBottom: "var(--ui-space-4)",
              paddingRight: "var(--ui-space-8)",
              ...rowIndent(depth),
            }}
          >
            This directory hit the listing cap — some entries are not shown.
          </p>
        </li>
      ) : null}
    </>
  );
}

/** One folder row plus, when expanded, its listing's
 * states and rows. The folder's own listing query lives
 * here: expansion enables the fetch, and the query stays
 * subscribed while the row is mounted, so a listing
 * loaded earlier still drives the loaded-but-empty
 * visibility rule after the folder is collapsed again. */
function FolderItem({
  projectId,
  folder,
  depth,
  showAll,
  selected,
  onSelect,
  expanded,
  onToggle,
}: {
  projectId: string;
  folder: RepoTreeFolder;
  depth: number;
  showAll: boolean;
  selected: string | null;
  onSelect: (path: string) => void;
  expanded: Set<string>;
  onToggle: (path: string) => void;
}) {
  const queryClient = useQueryClient();
  const checkout = useCheckout();
  const open = !folder.collapsed && expanded.has(folder.path);
  const query = useDirListing(projectId, folder.path, open);
  const listing = listingOf(query);
  const error = errorOf(query);

  if (!showAll && folder.hidden) return null;
  if (!showAll && !folder.collapsed && listing) {
    if (!listingHasVisibleContent(listing, queryClient, projectId, showAll, checkout)) return null;
  }

  return (
    <li>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--ui-space-4)",
          minHeight: "32px",
          paddingTop: "var(--ui-space-4)",
          paddingBottom: "var(--ui-space-4)",
          paddingRight: "var(--ui-space-8)",
          ...rowIndent(depth),
        }}
      >
        <Button
          variant="ghost"
          iconOnly
          disabled={folder.collapsed}
          ariaLabel={open ? `Collapse ${folder.path}` : `Expand ${folder.path}`}
          onClick={() => onToggle(folder.path)}
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        </Button>
        <span
          className="mono"
          style={{
            fontSize: "var(--ui-font-size-sm)",
            fontWeight: 600,
            overflowWrap: "anywhere",
          }}
        >
          {baseName(folder.path)}/
        </span>
        {folder.collapsed ? <span style={metaStyle}>pruned — contents not listed</span> : null}
        {folder.hidden ? <span style={metaStyle}>hidden</span> : null}
      </div>
      {open ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {query.isPending ? (
            <li
              style={{
                ...metaStyle,
                minHeight: "32px",
                display: "flex",
                alignItems: "center",
                paddingRight: "var(--ui-space-8)",
                ...rowIndent(depth + 1),
                paddingLeft: `calc(var(--ui-space-12) + ${depth + 1} * var(--ui-space-16) + 38px)`,
              }}
            >
              Loading…
            </li>
          ) : error ? (
            <li
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--ui-space-8)",
                minHeight: "32px",
                paddingRight: "var(--ui-space-8)",
                ...rowIndent(depth + 1),
                paddingLeft: `calc(var(--ui-space-12) + ${depth + 1} * var(--ui-space-16) + 38px)`,
              }}
            >
              <span style={{ ...metaStyle, whiteSpace: "normal", color: "var(--ui-danger)" }}>
                {error}
              </span>
              <Button variant="ghost" onClick={() => query.refetch()}>
                Retry
              </Button>
            </li>
          ) : listing ? (
            <DirLevel
              projectId={projectId}
              listing={listing}
              depth={depth + 1}
              showAll={showAll}
              selected={selected}
              onSelect={onSelect}
              expanded={expanded}
              onToggle={onToggle}
            />
          ) : null}
        </ul>
      ) : null}
    </li>
  );
}

export function FileTree({
  projectId,
  selected,
  onSelect,
}: {
  projectId: string;
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const queryClient = useQueryClient();
  const checkout = useCheckout();
  const [showAll, setShowAll] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const rootQuery = useDirListing(projectId, "", true);
  const rootListing = listingOf(rootQuery);
  const rootError = errorOf(rootQuery);

  const onToggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  return (
    <div data-anchor="repos/file-tree">
      <div style={{ padding: "var(--ui-space-8) var(--ui-space-12)" }}>
        <Toggle checked={showAll} onChange={setShowAll} label="Show hidden & ignored" />
      </div>
      {rootQuery.isPending ? (
        <p style={{ color: "var(--ui-content-muted)", padding: "0 var(--ui-space-12)" }}>
          Loading the file tree…
        </p>
      ) : rootError ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--ui-space-8)",
            padding: "0 var(--ui-space-12) var(--ui-space-8)",
          }}
        >
          <span style={{ color: "var(--ui-danger)", fontSize: "var(--ui-font-size-sm)" }}>
            {rootError}
          </span>
          <Button variant="ghost" onClick={() => rootQuery.refetch()}>
            Retry
          </Button>
        </div>
      ) : rootListing ? (
        <>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <DirLevel
              projectId={projectId}
              listing={rootListing}
              depth={0}
              showAll={showAll}
              selected={selected}
              onSelect={onSelect}
              expanded={expanded}
              onToggle={onToggle}
            />
          </ul>
          {!listingHasVisibleContent(rootListing, queryClient, projectId, showAll, checkout) ? (
            <p style={{ color: "var(--ui-content-muted)", padding: "0 var(--ui-space-12)" }}>
              Nothing to show with hidden &amp; ignored files off.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
