import { useMemo, useRef, useState } from "react";
import { Columns3, Search, Settings } from "lucide-react";
import {
  PhoneShell,
  SidebarNav,
  TopBar,
  type AppShellNavItem,
} from "@kit/components/shell/AppShell";
import { useIsPhone } from "@kit/lib/responsive";
import { useAdapter, useStoreVersion } from "../lib/store";
import { sidebarKey, useNav, type NavTarget } from "../lib/nav";

// The one shell (contract 09): the kit AppShell family owns
// the chrome — this component supplies the app's name, tile,
// destinations, live count badges, crumb, and global search,
// and keeps its route state in the nav context.
//
// Composition note: the desktop presentation is composed
// from the kit's exported SidebarNav + TopBar with an
// unpadded content column, rather than the AppShell's
// built-in content frame. That frame insets content by
// 22px/26px — exactly the inset every view in this app
// already carries (they were authored against an unpadded
// frame), so the built-in frame would double every inset
// against the storyboard exhibits. The phone presentation
// is the kit PhoneShell whole: its navbar carries the
// screen title (the view-level LargeTitle is suppressed at
// the kit breakpoint in app.css, the Runner pattern), root
// sections open from its grouped-list index, and pushed
// detail screens carry phoneTitle/phoneBack.
//
// Full-bleed sections (browse, peek, editor — storyboard
// frames 15–19) keep their section-owned forms: on desktop
// the TopBar leaves and the sidebar stays; on phone the
// section renders bare, as its phone exhibits are
// self-contained screens hanging off the same useIsPhone
// seam inside the sections themselves.

const NAV_ITEMS: { key: string; label: string; target: NavTarget }[] = [
  { key: "home", label: "Home", target: { section: "home" } },
  { key: "overview", label: "Overview", target: { section: "overview" } },
  { key: "goals", label: "Goals", target: { section: "goals" } },
  { key: "mockups", label: "Mockups", target: { section: "mockups" } },
  { key: "entries", label: "Entries", target: { section: "entries" } },
  { key: "plans", label: "Plans", target: { section: "plans" } },
  { key: "todos", label: "Todos", target: { section: "todos" } },
  { key: "board", label: "Board", target: { section: "board" } },
  { key: "inbox", label: "Inbox", target: { section: "inbox" } },
  { key: "taskmanager", label: "Task Manager", target: { section: "taskmanager" } },
  { key: "code", label: "Code", target: { section: "code" } },
];

const TARGETS: Record<string, NavTarget> = Object.fromEntries(
  NAV_ITEMS.map((i) => [i.key, i.target]),
);

function crumbFor(
  nav: NavTarget,
  project: string,
  goalTitle?: string,
): { left: string; bold: string } {
  switch (nav.section) {
    case "home":
      return { left: "Workbench", bold: "Home" };
    case "overview":
      return { left: project, bold: "Overview" };
    case "goals":
      return { left: "Workbench", bold: "Goals" };
    case "goal":
      return { left: "Goals", bold: goalTitle ?? "Goal" };
    case "mockups":
      return { left: project, bold: "Mockups" };
    case "mockup":
      return { left: "Mockups", bold: "Drill-in" };
    case "entries":
      return { left: project, bold: "Entries" };
    case "plans":
      return { left: project, bold: "Plans" };
    case "todos":
      return { left: project, bold: "Todos" };
    case "board":
      return { left: project, bold: "Board" };
    case "inbox":
      return { left: "Workbench", bold: "Inbox" };
    case "taskmanager":
      return { left: "Workbench", bold: "Task Manager" };
    case "code":
      return { left: project, bold: "Code" };
    case "repo":
      return { left: "Code", bold: nav.repo };
    case "browse":
      return { left: nav.repo, bold: "Files" };
    case "peek":
      return { left: nav.repo, bold: nav.path.split("/").pop() ?? "" };
    case "editor":
      return { left: nav.repo, bold: nav.path.split("/").pop() ?? "" };
    case "settings":
      return { left: "Settings", bold: "Workbench" };
  }
}

export function Shell({
  children,
  hideTopbar = false,
}: {
  children: React.ReactNode;
  hideTopbar?: boolean;
}) {
  useStoreVersion();
  const a = useAdapter();
  const { nav, navigate, project, setProject } = useNav();
  const isPhone = useIsPhone();

  const active = sidebarKey(nav);
  const counts = a.counts();
  const triageHere = a
    .entries(project)
    .filter((e) => e.kind === "mockup" && e.review === "in-triage").length;

  // Live count badges, as registered by the sections that own
  // them (the Goals badge is counts().goalsActive, exactly as
  // the Goals build registered it).
  const badges: Record<string, { count: number; hot?: boolean } | undefined> = {
    goals: counts.goalsActive > 0 ? { count: counts.goalsActive } : undefined,
    mockups: triageHere > 0 ? { count: triageHere } : undefined,
    board: counts.boardDoing > 0 ? { count: counts.boardDoing } : undefined,
    inbox:
      counts.inboxAwaiting > 0 ? { count: counts.inboxAwaiting, hot: true } : undefined,
  };

  const navItems: AppShellNavItem[] = NAV_ITEMS.map((item) => ({
    key: item.key,
    label: item.label,
    count: badges[item.key]?.count,
    hot: badges[item.key]?.hot,
  }));
  const footerNavItems: AppShellNavItem[] = [
    { key: "settings", label: "Settings", icon: <Settings size={17} aria-hidden /> },
  ];

  const onNavigate = (key: string) => {
    if (key === "settings") {
      navigate({ section: "settings" });
      return;
    }
    const target = TARGETS[key];
    if (target) navigate(target);
  };
  // The Apps back-row returns to the launcher in the
  // integrated shell (contract 09) — in this standalone
  // preview it returns Home.
  const onApps = () => navigate({ section: "home" });

  const crumb = crumbFor(
    nav,
    project,
    nav.section === "goal" ? a.goal(nav.slug)?.title : undefined,
  );
  const crumbEl = (
    <span className="min-w-0 flex-1 truncate text-[13.5px]" style={{ color: "var(--wb-content-secondary)" }}>
      {crumb.left} / <b style={{ color: "var(--wb-content-primary)" }}>{crumb.bold}</b>
    </span>
  );

  // Pushed detail screens on phone: the PhoneShell navbar is
  // titled by the record and backs out to its section index.
  const phoneTitle =
    nav.section === "goal"
      ? a.goal(nav.slug)?.title
      : nav.section === "mockup"
        ? a.entry(nav.entryId)?.title
        : nav.section === "repo"
          ? a.repo(nav.repo)?.name
          : undefined;
  const phoneBack =
    nav.section === "goal"
      ? { label: "Goals", onClick: () => navigate({ section: "goals" }) }
      : nav.section === "mockup"
        ? { label: "Mockups", onClick: () => navigate({ section: "mockups" }) }
        : nav.section === "repo"
          ? { label: "Code", onClick: () => navigate({ section: "code" }) }
          : undefined;

  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const out: { label: string; sub: string; go: () => void }[] = [];
    for (const p of a.projects()) {
      if (p.slug.includes(q) || p.name.toLowerCase().includes(q)) {
        out.push({
          label: p.name,
          sub: "Project",
          go: () => {
            setProject(p.slug);
            navigate({ section: "overview" });
          },
        });
      }
    }
    for (const p of a.projects()) {
      for (const e of a.entries(p.slug)) {
        if (e.title.toLowerCase().includes(q)) {
          out.push({
            label: e.title,
            sub: `Entry · ${p.slug}`,
            go: () => {
              setProject(p.slug);
              navigate(e.kind === "mockup" ? { section: "mockup", entryId: e.id } : { section: "entries" });
            },
          });
        }
      }
      for (const pl of a.plans(p.slug)) {
        if (pl.title.toLowerCase().includes(q)) {
          out.push({
            label: pl.title,
            sub: `Plan · ${p.slug}`,
            go: () => {
              setProject(p.slug);
              navigate({ section: "plans", bundle: pl.bundle });
            },
          });
        }
      }
      for (const t of a.todos(p.slug)) {
        if (t.title.toLowerCase().includes(q)) {
          out.push({
            label: t.title,
            sub: `Todo · ${p.slug}`,
            go: () => {
              setProject(p.slug);
              navigate({ section: "todos" });
            },
          });
        }
      }
    }
    for (const g of a.allGoals()) {
      if (g.title.toLowerCase().includes(q)) {
        out.push({
          label: g.title,
          sub: `Goal · ${g.project}`,
          go: () => {
            setProject(g.project);
            navigate({ section: "goal", slug: g.slug });
          },
        });
      }
    }
    for (const r of a.repos()) {
      if (r.slug.includes(q)) {
        out.push({ label: r.name, sub: "Repo", go: () => navigate({ section: "repo", repo: r.slug }) });
      }
    }
    return out.slice(0, 8);
  }, [query, a, navigate, setProject]);

  const searchBox = (phone: boolean) => (
    <div className={phone ? "relative w-full" : "relative"} ref={searchRef}>
      <div
        className={`flex items-center gap-2 rounded-[9px] px-3 py-1.5 ${phone ? "w-full" : "w-[210px] max-w-[34vw]"}`}
        style={{ backgroundColor: "var(--wb-surface-sunken)" }}
      >
        <Search size={14} className="shrink-0" style={{ color: "var(--wb-content-muted)" }} />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSearchOpen(true);
          }}
          onFocus={() => setSearchOpen(true)}
          onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
          placeholder="Search everything"
          aria-label="Search everything"
          className="w-full min-w-0 bg-transparent text-[13.5px] outline-none"
          style={{ color: "var(--wb-content-primary)" }}
        />
      </div>
      {searchOpen && results.length > 0 ? (
        <div
          className={`absolute top-[110%] z-40 overflow-hidden ${phone ? "right-0 left-0 w-auto" : "right-0 w-[320px] max-w-[86vw]"}`}
          style={{
            backgroundColor: "var(--wb-surface-2)",
            border: "1px solid var(--wb-border-default)",
            borderRadius: "var(--wb-radius-md)",
            boxShadow: "var(--wb-shadow-overlay)",
          }}
        >
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                r.go();
                setSearchOpen(false);
                setQuery("");
              }}
              className="block w-full px-3.5 py-2.5 text-left"
              style={{ borderBottom: i < results.length - 1 ? "1px solid var(--wb-border-default)" : undefined }}
            >
              <div className="truncate text-sm font-medium">{r.label}</div>
              <div className="truncate text-xs" style={{ color: "var(--wb-content-secondary)" }}>{r.sub}</div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );

  const shellProps = {
    appName: "Workbench",
    appIcon: <Columns3 size={19} aria-hidden />,
    appTileStyle: {
      background: "linear-gradient(160deg,#14b8a6,#0f766e)",
    },
    navItems,
    footerNavItems,
    active,
    onNavigate,
    onApps,
  };

  if (isPhone) {
    if (hideTopbar) {
      // Full-bleed phone sections are self-contained screens
      // (frames 15–19) — they render bare, as before.
      return (
        <div
          className="flex h-full flex-col"
          style={{ backgroundColor: "var(--wb-surface-canvas)", color: "var(--wb-content-primary)" }}
        >
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>
      );
    }
    return (
      <PhoneShell
        {...shellProps}
        search={searchBox(true)}
        phoneTitle={phoneTitle}
        phoneBack={phoneBack}
      >
        {children}
      </PhoneShell>
    );
  }

  return (
    <div
      className="flex h-full"
      style={{ backgroundColor: "var(--wb-surface-canvas)", color: "var(--wb-content-primary)" }}
    >
      <SidebarNav {...shellProps} />
      <div className="flex min-w-0 flex-1 flex-col">
        {hideTopbar ? null : <TopBar crumb={crumbEl} search={searchBox(false)} />}
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
