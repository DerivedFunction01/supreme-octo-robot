// Integration entry — the form of the workbench app that
// the Workhorse Superapp shell embeds in an iframe (the
// Scheduler/Runner integration-entry pattern: the
// standalone preview harness in main.tsx stays behind;
// this entry runs the data selection below, then loads
// the mounted tree in embedded.tsx).
//
// Data selection (the live-feed cure, 2026-11-15 — the
// published form previously mounted the mock with nothing
// saying so, because the feeds document existed only as a
// serving-shell injection the artifact never made):
// - A document already injected as __WORKBENCH_FEEDS__
//   (the serving shell's original topology) mounts as-is;
//   no fetch is made.
// - Otherwise the entry fetches the document from
//   GET /api/feeds on the workrecord surface — same-origin
//   by default, or ?api=<base-url> for an explicit base —
//   injects it as __WORKBENCH_FEEDS__ (with the base as
//   __WORKBENCH_API_BASE__, which prefixes the live
//   adapter's own fetches), and only then loads the app
//   module graph, so live mode never flashes the mock or
//   an empty state.
// - ?adapter=mock mounts the stateful mock (the demo
//   persona) explicitly — the operator's override, which
//   wins over an injected document as well.
// - ?transport=relay is the rebuilt superapp's frame
//   form (REBUILD STEP 3): no HTTP fetch is possible or
//   wanted — the entry asks the shell for the document
//   through the workhorse:* postMessage relay (the
//   getFeeds action, executed by the shell over the
//   privileged bridge) and injects the relay channel as
//   __WORKBENCH_CHANNEL__, so the live adapter's every
//   call rides the relay beneath the same seam. The
//   standalone and current shell embeds keep HTTP.
// A failed fetch mounts nothing and says so in the root,
// with the URL it tried and a reload action: serving the
// mock as if it were live is the defect this entry exists
// to cure, so the refusal is explicit, never a fallback.
import type { WorkbenchFeeds } from "./lib/feeds";
import { relayChannel, type WbChannel } from "./lib/transport";

const params = new URLSearchParams(window.location.search);
const rootEl = document.getElementById("root") as HTMLElement;

type WorkbenchGlobals = {
  __WORKBENCH_FEEDS__?: WorkbenchFeeds;
  __WORKBENCH_API_BASE__?: string;
  __WORKBENCH_CHANNEL__?: WbChannel;
};

function note(text: string) {
  rootEl.replaceChildren();
  const p = document.createElement("p");
  p.textContent = text;
  p.style.cssText =
    "font: 14px/1.5 system-ui, sans-serif; margin: 24px 16px;";
  rootEl.append(p);
}

function failure(url: string, err: unknown) {
  rootEl.replaceChildren();
  const wrap = document.createElement("div");
  wrap.style.cssText =
    "font: 14px/1.5 system-ui, sans-serif; margin: 24px 16px;";
  const head = document.createElement("p");
  head.textContent = "Live workbench unavailable";
  head.style.cssText = "font-weight: 600; margin: 0 0 8px;";
  const detail = document.createElement("p");
  detail.textContent =
    `The live feeds could not be loaded from ${url} — ` +
    `${err instanceof Error ? err.message : String(err)}. ` +
    "Nothing is shown rather than demo data in its place.";
  detail.style.cssText = "margin: 0 0 12px;";
  const reload = document.createElement("button");
  reload.textContent = "Reload";
  reload.addEventListener("click", () => window.location.reload());
  wrap.append(head, detail, reload);
  rootEl.append(wrap);
}

async function boot(): Promise<void> {
  const g = globalThis as WorkbenchGlobals;
  if (params.get("adapter") === "mock") {
    // The explicit opt-out: drop any injected document so
    // the seam falls back to the mock (see store.tsx).
    delete g.__WORKBENCH_FEEDS__;
    delete g.__WORKBENCH_API_BASE__;
    delete g.__WORKBENCH_CHANNEL__;
  } else if (params.get("transport") === "relay") {
    // The frame form: the channel is injected first (the
    // adapter's own calls ride it), and the document —
    // when not already injected — rides the relay's
    // getFeeds action, executed by the shell over the
    // privileged bridge.
    const channel = relayChannel();
    g.__WORKBENCH_CHANNEL__ = channel;
    if (!g.__WORKBENCH_FEEDS__) {
      note("Loading the live workbench…");
      try {
        const env = await channel("getFeeds");
        if (env.status !== 200 || env.payload == null) {
          throw new Error(
            env.error ?? `the bridge answered status ${env.status}`,
          );
        }
        g.__WORKBENCH_FEEDS__ = env.payload as WorkbenchFeeds;
      } catch (err) {
        failure("the shell relay (workbench.getFeeds)", err);
        return;
      }
    }
  } else if (!g.__WORKBENCH_FEEDS__) {
    const apiBase = (params.get("api") ?? "").replace(/\/+$/, "");
    const url = `${apiBase}/api/feeds`;
    note("Loading the live workbench…");
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`the surface answered ${res.status}`);
      }
      g.__WORKBENCH_FEEDS__ = (await res.json()) as WorkbenchFeeds;
      g.__WORKBENCH_API_BASE__ = apiBase;
    } catch (err) {
      failure(url, err);
      return;
    }
  }
  // The globals above are set before this import's module
  // graph (which reads them at the seam) evaluates.
  await import("./embedded");
}

void boot();

export {};
