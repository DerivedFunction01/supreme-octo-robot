// Integration entry — the form of the attention app that the
// Workhorse Superapp shell embeds in an iframe (the
// Scheduler/Runner integration-entry pattern: the standalone
// preview harness in App.tsx stays behind; this entry mounts
// the app itself inside the kit's AppShell).
//
// The store is the LIVE attention backend by default —
// same-origin api/1, and `?adapter=mock` is the explicit
// opt-out that mounts the mock store. The live store's
// first load is awaited before mounting, so the published
// app never opens on an empty snapshot.
//
// The live base is the serving origin, full stop: no
// query parameter names another base. (The ?api=
// override this entry once read was removed as a HIGH
// finding, 2026-11-16 — it had no legitimate uses in the
// tree, and a crafted link could have pointed the store,
// writes included, at an arbitrary base. Defence in
// depth rides the seam: transport.ts's sanitizeBaseUrl
// honours only "" or a same-origin relative path, so no
// injection can point the store off-origin.)
//
// `?transport=relay` is the rebuild frame's form (step 3):
// the same live store, its channel swapped for the shell
// relay — every call rides workhorse:* postMessage to the
// shell's action client instead of fetching the backend
// origin (transport.ts). The default stays HTTP, so the
// current shell embed is untouched.
//
// Cross-app sync with the shell runs over postMessage,
// mirroring the shell's existing `workhorse:apps` bridge:
//   shell -> app: { type: "workhorse:attention-sync",
//                   presence?: boolean | "active" | "away" | "focus",
//                   digest?: string }
//     Applied through the store's own setters — the shell's
//     Presence switch drives setPresence, its Digest window
//     row drives setDigestWindow — never by patching the DOM.
//   app -> shell: { type: "workhorse:attention-count", count }
//     Posted on mount and on every store change, so the
//     shell's launcher tile badge and Today widget always
//     carry this store's live decision count.
//   app -> shell: { type: "workhorse:attention-ready" }
//     Posted once on mount; the shell answers by pushing its
//     current presence/digest state.
// Theme follows the shell the same way the other embedded
// apps do: the shell's data-palette / data-mode / data-density
// are read from the parent document and kept in step with a
// MutationObserver, then handed to the app as its palette /
// mode / density (the app renders those attributes on its
// root — the shell's unified Settings owns the axes).
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./app.css";
import { AppMain } from "./App";
import { LiveAttentionStore } from "./attention/live-store";
import { RelayTransport } from "./attention/transport";
import type { AttentionDataSource } from "./attention/types";
import { DataContext } from "./attention/useStore";
import type { ModeValue } from "@workhorse/kit/components/ModeControl";

/** The shell's digest row cycles the times the digest can
 * fire; each maps onto the store's digest windows so that
 * the chosen time becomes the next window the app derives
 * (Today's subtitle and due row, the Digest view's next
 * window). The seed state is the "3:00 PM" row: Morning and
 * Midday enabled, Evening off. */
const DIGEST_WINDOWS: Record<string, Record<string, boolean>> = {
  "3:00 PM": { morning: true, midday: true, evening: false },
  "8:00 PM": { morning: true, midday: false, evening: true },
  "8:00 AM": { morning: true, midday: false, evening: false },
};

function parentAttr(name: string): string | null {
  try {
    return window.parent.document.documentElement.getAttribute(name);
  } catch {
    return null;
  }
}

function IntegrationRoot({ store }: { store: AttentionDataSource }) {
  const [palette, setPalette] = useState(() => parentAttr("data-palette") ?? "olive");
  const [mode, setMode] = useState<ModeValue>(() => {
    const m = parentAttr("data-mode");
    return m === "dark" || m === "light" ? m : "system";
  });
  const [density, setDensity] = useState(
    () => parentAttr("data-density") ?? "comfortable",
  );

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

  // Waiting count -> shell (launcher badge + Today widget).
  useEffect(() => {
    const post = () => {
      try {
        window.parent.postMessage(
          {
            type: "workhorse:attention-count",
            count: store.getToday().decision_count,
          },
          "*",
        );
      } catch {
        /* no parent (standalone open): nothing to drive */
      }
    };
    post();
    try {
      window.parent.postMessage({ type: "workhorse:attention-ready" }, "*");
    } catch {
      /* as above */
    }
    return store.subscribe(post);
  }, [store]);

  // Shell Settings -> store setters (presence + digest).
  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      const data = ev.data as {
        type?: string;
        presence?: unknown;
        digest?: unknown;
      } | null;
      if (!data || data.type !== "workhorse:attention-sync") return;
      if (
        data.presence === "active" ||
        data.presence === "away" ||
        data.presence === "focus"
      ) {
        // The three-state form (AC-11): the shell may name
        // the mode directly — Focus included, which the
        // boolean form below cannot reach.
        store.setPresence(data.presence, data.presence === "active" ? "17:00" : "none");
      } else if (typeof data.presence === "boolean") {
        // The shell's switch is two-state: on is the seeded
        // Active form (until 5:00 PM, matching the app's own
        // chip label); off holds items for the digest, which
        // is the store's Away mode.
        if (data.presence) store.setPresence("active", "17:00");
        else store.setPresence("away", "none");
      }
      if (typeof data.digest === "string") {
        const windows = DIGEST_WINDOWS[data.digest];
        if (windows) {
          for (const [id, enabled] of Object.entries(windows)) {
            store.setDigestWindow(id, enabled);
          }
        }
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [store]);

  return (
    <DataContext.Provider value={store}>
      <AppMain embedded palette={palette} mode={mode} density={density} />
    </DataContext.Provider>
  );
}

function mount(store: AttentionDataSource) {
  createRoot(document.getElementById("root") as HTMLElement).render(
    <StrictMode>
      <IntegrationRoot store={store} />
    </StrictMode>,
  );
}

const params = new URLSearchParams(window.location.search);
if (params.get("adapter") === "mock") {
  // Dynamic import only: the mock store (and its seed data)
  // must not ride the main integration bundle — it splits
  // into a lazy chunk the shell loads only for ?adapter=mock.
  void import("./attention/store").then(({ createMockAttentionStore }) =>
    mount(createMockAttentionStore()),
  );
} else {
  const live =
    params.get("transport") === "relay"
      ? new LiveAttentionStore({ transport: new RelayTransport() })
      : new LiveAttentionStore();
  void live.ready().then(() => mount(live));
}
