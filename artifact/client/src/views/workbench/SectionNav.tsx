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
        gap: "var(--wb-space-4)",
        background: "var(--wb-surface-2)",
        border: "1px solid var(--wb-border-default)",
        borderRadius: "var(--wb-radius-lg)",
        padding: "var(--wb-space-4)",
        marginBottom: "var(--wb-space-16)",
      }}
    >
      {(["overview", "entries", "plans", "todos", "board"] as SectionId[]).map((section) => {
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
              padding: "var(--wb-space-8) 2px",
              borderRadius: "var(--wb-radius-md)",
              border: isCurrent ? "1px solid var(--wb-border-default)" : "1px solid transparent",
              background: isCurrent ? "var(--wb-surface-1)" : "transparent",
              boxShadow: isCurrent ? "var(--wb-shadow-overlay)" : "none",
              color: isCurrent ? "var(--wb-content-primary)" : "var(--wb-content-secondary)",
              fontSize: "var(--wb-font-size-xs)",
              lineHeight: "var(--wb-line-height-xs)",
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
