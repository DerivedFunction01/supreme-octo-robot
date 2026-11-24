import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Shell } from "./components/Shell";
import { ActionRow, Group } from "./components/ui";
import {
  NavContext,
  type EditorGuard,
  type NavTarget,
} from "./lib/nav";
import { adapter } from "./lib/store";
import { Home } from "./sections/Home";
import { Overview } from "./sections/Overview";
import { GoalDetail, Goals } from "./sections/Goals";
import { MockupDetail, Mockups } from "./sections/Mockups";
import { Entries } from "./sections/Entries";
import { Plans } from "./sections/Plans";
import { Todos } from "./sections/Todos";
import { Board } from "./sections/Board";
import { Inbox } from "./sections/Inbox";
import { MessageThreads } from "./sections/MessageThreads";
import { RepoDetail } from "./sections/Repos";
import { TaskManager } from "./sections/TaskManager";
import { Browse, PeekPage } from "./sections/Explorer";
import { Editor } from "./sections/Editor";
import { Settings } from "./sections/Settings";

// The workbench app over the mock adapter. All state lives
// behind the seam (lib/seam.ts); this component owns only
// navigation and the editor's discard guard (frame 13).

const FULL_BLEED = new Set(["browse", "peek", "editor"]);

export function App() {
  const [nav, setNav] = useState<NavTarget>({ section: "home" });
  const [project, setProject] = useState("spec-driven-starter");
  const [pendingNav, setPendingNav] = useState<NavTarget | null>(null);
  const guardRef = useRef<EditorGuard | null>(null);
  const [, setGuardTick] = useState(0);

  // Freshness (W14): a standing 30-second refresh pulse
  // over the seam — the freshness labels on Home and the
  // Board read the adapter's last-refresh stamp.
  useEffect(() => {
    const id = window.setInterval(() => {
      void adapter.refresh();
    }, 30_000);
    return () => window.clearInterval(id);
  }, []);

  // Mode: default follows the OS (kit sheet); palette olive.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.mode = mq.matches ? "dark" : "light";
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const setEditorGuard = useCallback((g: EditorGuard | null) => {
    guardRef.current = g;
    setGuardTick((n) => n + 1);
  }, []);

  const navigate = useCallback(
    (t: NavTarget) => {
      // Leaving the editor with unsaved edits raises the
      // discard guard (frame 13) instead of navigating.
      if (guardRef.current && nav.section === "editor" && t.section !== "editor") {
        setPendingNav(t);
        return;
      }
      setNav(t);
    },
    [nav.section],
  );

  const api = useMemo(
    () => ({ nav, navigate, project, setProject, setEditorGuard }),
    [nav, navigate, project, setEditorGuard],
  );

  const guard = guardRef.current;

  return (
    <NavContext.Provider value={api}>
      <Shell hideTopbar={FULL_BLEED.has(nav.section)}>
        {nav.section === "home" ? <Home /> : null}
        {nav.section === "overview" ? <Overview /> : null}
        {nav.section === "goals" ? <Goals /> : null}
        {nav.section === "goal" ? <GoalDetail key={nav.slug} slug={nav.slug} /> : null}
        {nav.section === "mockups" ? <Mockups /> : null}
        {nav.section === "mockup" ? <MockupDetail key={nav.entryId} entryId={nav.entryId} /> : null}
        {nav.section === "entries" ? <Entries /> : null}
        {nav.section === "plans" ? (
          <Plans key={`${project}/${nav.bundle ?? ""}`} initialBundle={nav.bundle} />
        ) : null}
        {nav.section === "todos" ? <Todos key={project} /> : null}
        {nav.section === "taskmanager" ? <TaskManager /> : null}
        {nav.section === "board" ? <Board /> : null}
        {nav.section === "inbox" ? (
          <>
            <Inbox />
            <MessageThreads />
          </>
        ) : null}
        {nav.section === "code" ? <RepoDetail key={project} repoSlug={project} /> : null}
        {nav.section === "repo" ? <RepoDetail repoSlug={nav.repo} /> : null}
        {nav.section === "browse" ? <Browse repoSlug={nav.repo} trail={nav.path} /> : null}
        {nav.section === "peek" ? <PeekPage repoSlug={nav.repo} path={nav.path} /> : null}
        {nav.section === "editor" ? (
          <Editor key={`${nav.repo}/${nav.path}`} repoSlug={nav.repo} path={nav.path} />
        ) : null}
        {nav.section === "settings" ? <Settings /> : null}
      </Shell>

      {pendingNav && guard ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: "rgb(16 18 10 / 0.45)" }}
          role="dialog"
          aria-modal="true"
          aria-label="Discard changes?"
        >
          <div
            className="w-[400px] max-w-[calc(100vw-32px)] p-[22px]"
            style={{
              backgroundColor: "var(--wb-surface-2)",
              borderRadius: 16,
              boxShadow: "0 18px 50px rgb(0 0 0 / 0.4)",
              color: "var(--wb-content-primary)",
            }}
          >
            <div className="mb-1.5 text-lg font-bold">Discard changes?</div>
            <p
              className="mb-4 text-sm leading-[1.45] [overflow-wrap:anywhere]"
              style={{ color: "var(--wb-content-secondary)" }}
            >
              {guard.fileName} has unsaved edits. Closing now discards them — the saved file stays
              at sha {guard.sha}.
            </p>
            <Group>
              <ActionRow label="Keep editing" onClick={() => setPendingNav(null)} />
              <ActionRow
                label="Save and close"
                onClick={() => {
                  void guard.save().then((result) => {
                    if (result.ok) {
                      const target = pendingNav;
                      setEditorGuard(null);
                      setPendingNav(null);
                      if (target) setNav(target);
                    } else {
                      // The refusal is on the editor's face; stay.
                      setPendingNav(null);
                    }
                  });
                }}
              />
              <ActionRow
                label="Discard changes"
                danger
                last
                onClick={() => {
                  guard.discard();
                  const target = pendingNav;
                  setEditorGuard(null);
                  setPendingNav(null);
                  if (target) setNav(target);
                }}
              />
            </Group>
          </div>
        </div>
      ) : null}
    </NavContext.Provider>
  );
}
