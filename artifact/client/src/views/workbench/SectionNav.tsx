// The project section nav — ported from the original
// viewer's PhoneSectionNav (sections/shell/PhoneChrome):
// the rail's Sections list as a segmented row, rendered
// inside the body. In the standalone viewer the desktop
// presentation carried the same list in its rail; in the
// one client the shell's sidebar carries the app-level
// destinations only, so this in-view row is the section
// navigation on every presentation. Its hrefs are the
// routing seam's full client hashes (lib/routing).

import { sectionLabel } from "./lib/labels";
import { type SectionId, sectionHref } from "./lib/routing";

export function SectionNav({ slug, current }: { slug: string; current: SectionId }) {
  return (
    <nav
      data-anchor="shell/section-nav"
      aria-label="Project sections"
      style={{
        display: "flex",
        gap: "var(--ui-space-4)",
        background: "var(--ui-surface-2)",
        border: "1px solid var(--ui-border-default)",
        borderRadius: "var(--ui-radius-lg)",
        padding: "var(--ui-space-4)",
        marginBottom: "var(--ui-space-16)",
      }}
    >
      {(["overview", "entries", "plans", "todos", "board", "code"] as SectionId[]).map((section) => {
        const isCurrent = section === current;
        return (
          <a
            key={section}
            href={sectionHref(slug, section)}
            aria-current={isCurrent ? "page" : undefined}
            style={{
              flex: "1 1 0",
              minWidth: 0,
              minHeight: "38px",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "var(--ui-space-8) 2px",
              borderRadius: "var(--ui-radius-md)",
              border: isCurrent ? "1px solid var(--ui-border-default)" : "1px solid transparent",
              background: isCurrent ? "var(--ui-surface-1)" : "transparent",
              boxShadow: isCurrent ? "var(--ui-shadow-overlay)" : "none",
              color: isCurrent ? "var(--ui-content-primary)" : "var(--ui-content-secondary)",
              fontSize: "var(--ui-font-size-xs)",
              lineHeight: "var(--ui-line-height-xs)",
              fontWeight: isCurrent ? 700 : 500,
              textDecoration: "none",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {sectionLabel(section)}
          </a>
        );
      })}
    </nav>
  );
}
