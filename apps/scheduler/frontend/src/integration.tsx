// Integration entry — the form of the scheduler app that the
// Workhorse Superapp shell embeds in an iframe (the
// Attention/Runner integration-entry pattern: the standalone
// preview harness in Preview.tsx stays behind; this entry
// mounts the app itself, on the live adapter by default,
// inside the kit's AppShell).
//
// Adapter selection: the default is the LIVE adapter over
// the pipeline's /api/v1 — same-origin, full stop: the live
// base is the serving origin and no query parameter or
// injected value can repoint it (the ?api= base override
// was removed 2026-11-16, the HIGH finding the runner
// entry's cure at b54ebb2 diagnosed: the adapter POSTs the
// graduated config write to its base, so a crafted link
// carrying ?api= could have pointed that write at an
// arbitrary origin; the seam sanitizer in the live adapter
// refuses any non-same-origin base as defence in depth) —
// and the app mounts
// immediately, ahead of the first snapshot: the views render
// the adapter's pre-live states ("connecting" while an
// attempt is in flight, "unreachable" only once one has
// failed) and adopt served data as it lands. ?adapter=mock mounts the
// stateful mock (the demo persona) explicitly; the embedding
// shell passes no adapter parameter, so the published form
// is live by default (the silent-mock cure, 2026-11-15 —
// the shell's plain iframe src previously landed on the
// mock with nothing saying so).
//
// Shell-bridge intents: a family built-in's "Open in" row
// posts { type: "workhorse:open", app, job_id } to the parent
// shell — App's default onOpenInApp does exactly that, so this
// entry passes no override. Theme follows the shell the same
// way the other embedded apps do: the shell's data-palette /
// data-mode / data-density are read from the parent document
// and kept in step with a MutationObserver, then rendered as
// this root's attributes — the app itself carries no settings
// surface (the shell's unified Settings owns the axes).
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { ModeValue } from "@workhorse/kit/components/controls/ModeControl";
import { App } from "./App";
import type { SchedulerApi } from "./api";
import { LiveSchedulerApi } from "./live/live-adapter";
import { relayFetch } from "./live/relay";
import { mockApi } from "./mock/mock-adapter";
import "./index.css";

function parentAttr(name: string): string | null {
  try {
    return window.parent.document.documentElement.getAttribute(name);
  } catch {
    return null;
  }
}

function IntegrationRoot({ api }: { api: SchedulerApi }) {
  const [palette, setPalette] = useState(
    () => parentAttr("data-palette") ?? "olive",
  );
  const [mode, setMode] = useState<ModeValue>(() => {
    const m = parentAttr("data-mode");
    return m === "dark" || m === "light" ? m : "system";
  });
  const [density, setDensity] = useState(
    () => parentAttr("data-density") ?? "comfortable",
  );
  const [systemDark, setSystemDark] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  // Theme sync: follow the shell's palette/mode/density attributes.
  useEffect(() => {
    const sync = () => {
      const p = parentAttr("data-palette");
      if (p) setPalette(p);
      const m = parentAttr("data-mode");
      if (m === "dark" || m === "light") setMode(m);
      const d = parentAttr("data-density");
      if (d) setDensity(d);
    };
    sync();
    let observer: MutationObserver | null = null;
    try {
      observer = new MutationObserver(sync);
      observer.observe(window.parent.document.documentElement, {
        attributes: true,
        attributeFilter: ["data-palette", "data-mode", "data-density"],
      });
    } catch {
      /* standalone: keep the initial read */
    }
    return () => observer?.disconnect();
  }, []);

  const resolvedMode =
    mode === "system" ? (systemDark ? "dark" : "light") : mode;

  return (
    <div
      data-palette={palette}
      data-mode={resolvedMode}
      data-density={density}
      style={{ height: "100dvh" }}
    >
      <App api={api} />
    </div>
  );
}

function mount(api: SchedulerApi) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <IntegrationRoot api={api} />
    </StrictMode>,
  );
}

const params = new URLSearchParams(window.location.search);
if (params.get("adapter") === "mock") {
  mount(mockApi);
} else {
  // Channel selection (rebuild step 3): as a frame of the
  // workhorse shell — declared by the frame document's
  // [data-workhorse-frame="scheduler"] marker, or forced
  // with ?transport=relay — the live adapter rides the
  // shell relay (workhorse:* postMessage to the shell's
  // action client) instead of fetching /api/v1 directly;
  // standalone it fetches as before. The adapter, its
  // three-state reachability, and the mount order below
  // are the same in both channels.
  const useRelay =
    params.get("transport") === "relay" ||
    document.querySelector('[data-workhorse-frame="scheduler"]') !== null;
  const live = useRelay
    ? new LiveSchedulerApi({ fetchFn: relayFetch })
    : new LiveSchedulerApi();
  // Mount ahead of ready(): the shell renders immediately on
  // the empty snapshot — its status reads "connecting" while
  // the first attempt is in flight — and the adapter's emits
  // re-render the views as served data lands. Awaiting the
  // first snapshot before mounting would show nothing at all
  // for exactly the slow loads the connecting state exists
  // for. ready() still runs (it resolves even when the
  // bridge is down, and polling keeps retrying).
  mount(live);
  void live.ready();
}
