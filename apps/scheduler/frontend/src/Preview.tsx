// Standalone preview entry — the whole scheduler app running
// on the mock adapter, in a desk frame like the storyboard's.
// This harness is NOT part of the app: at integration the parent
// mounts <App api={liveAdapter}> inside the superapp shell and
// this file stays behind as the stage's demo entry.

import { useEffect, useState } from "react";
import { ModeControl, type ModeValue } from "@workhorse/kit/components/ModeControl";
import { PaletteSelect } from "@workhorse/kit/components/PaletteSelect";
import { App } from "./App";
import { mockApi } from "./mock/mock-adapter";

export function Preview() {
  const [palette, setPalette] = useState("olive");
  const [mode, setMode] = useState<ModeValue>("system");
  // The harness surfaces shell-bridge navigation intents
  // (a family built-in's "Open in" row) as text — in the
  // embedded form the same intent posts workhorse:open to
  // the parent shell, which routes it.
  const [intent, setIntent] = useState<string | null>(null);
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

  const resolvedMode =
    mode === "system" ? (systemDark ? "dark" : "light") : mode;

  return (
    <div
      className="flex min-h-screen flex-col items-center gap-4 px-5 py-7"
      style={{ color: "#eceeda" }}
    >
      <div className="flex w-full max-w-[920px] flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="m-0 text-[15px] font-semibold tracking-[0.02em]">
          Scheduler — stage D2 mock preview
        </h1>
        <p className="m-0 text-[13px]" style={{ color: "#c9cdb2" }}>
          Stateful mock adapter behind the contract-09 seam · every
          control works against the mock store · the live adapter
          swaps in at S8 with no frontend rewrite.
        </p>
        {/* Harness appearance controls: in the integrated build
            the shell's unified Settings owns the appearance axes
            and the app follows its root attributes; standalone,
            the harness plays the host and drives the frame's
            attributes from here. The app itself carries no
            settings surface. */}
        <span className="ml-auto inline-flex items-center gap-3">
          <PaletteSelect
            value={palette}
            options={[
              { id: "olive", label: "Olive" },
              { id: "teal", label: "Teal" },
            ]}
            onChange={setPalette}
          />
          <ModeControl value={mode} onChange={setMode} />
        </span>
      </div>
      <div
        className="w-full max-w-[920px] rounded-[18px] p-[9px]"
        style={{ background: "#0c0d08", boxShadow: "0 18px 50px rgb(0 0 0 / .5)" }}
      >
        {/* check-truncation-allow:T3 — the preview device
            frame: a fixed-height viewport the app shell
            scrolls inside, not a text container. */}
        <div
          data-palette={palette}
          data-mode={resolvedMode}
          className="h-[720px] overflow-hidden rounded-[10px]"
        >
          <App
            api={mockApi}
            onOpenInApp={(target, jobId) =>
              setIntent(
                `Shell navigation intent: workhorse:open → ${target} (${jobId})`,
              )
            }
          />
        </div>
      </div>
      {intent ? (
        <p
          role="status"
          className="m-0 w-full max-w-[920px] text-[13px]"
          style={{ color: "#c9cdb2" }}
        >
          {intent}
        </p>
      ) : null}
    </div>
  );
}
