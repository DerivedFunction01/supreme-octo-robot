import { useState } from "react";
import { ChevronLeft, Clock } from "lucide-react";
import { AppShell } from "@workhorse/kit/components/AppShell";
import { Button } from "@workhorse/kit/components/Button";
import { Input } from "@workhorse/kit/components/Fields";
import { Sheet } from "@workhorse/kit/components/Sheet";
import type { SchedulerApi } from "./api";
import type { OpenInTarget } from "./types";
import { useApiTick } from "./hooks";
import { Overview } from "./views/Overview";
import { Jobs } from "./views/Jobs";
import { JobDetail } from "./views/JobDetail";
import { Pings } from "./views/Pings";
import { Ledger } from "./views/Ledger";

export type Route =
  | { view: "overview" }
  | { view: "jobs" }
  | { view: "job"; jobId: string }
  | { view: "pings" }
  | { view: "ledger" };

const VIEW_TITLES: Record<Route["view"], string> = {
  overview: "Overview",
  jobs: "Jobs",
  job: "Jobs",
  pings: "Pings",
  ledger: "Ledger",
};

export function App({
  api,
  onOpenInApp,
}: {
  api: SchedulerApi;
  /** The shell-bridge navigation intent behind a family
   *  built-in's "Open in" row. The host (integration
   *  wrapper / preview harness) supplies it; the default
   *  posts the workhorse:open message to the parent shell —
   *  the postMessage convention the embedded apps use. */
  onOpenInApp?: (target: OpenInTarget, jobId: string) => void;
}) {
  useApiTick(api);
  const [route, setRoute] = useState<Route>({ view: "overview" });
  const [search, setSearch] = useState("");
  const [appsOpen, setAppsOpen] = useState(false);

  const pendingCount = api.listPings().length;
  // The Jobs badge counts the operator's jobs only (contract
  // 09, amendment 2026-11-13) — built-ins are not the
  // operator's list.
  const operatorCount = api
    .listJobs()
    .filter((j) => j.audience === "operator").length;

  const openInApp = (target: OpenInTarget, jobId: string) => {
    if (onOpenInApp) {
      onOpenInApp(target, jobId);
      return;
    }
    try {
      window.parent.postMessage(
        { type: "workhorse:open", app: target, job_id: jobId },
        "*",
      );
    } catch {
      /* no parent shell (standalone open): nothing to drive */
    }
  };

  const navigate = (next: Route) => {
    setRoute(next);
    setSearch("");
  };
  const openJob = (jobId: string) => navigate({ view: "job", jobId });

  // The one shell (contract 09): the kit AppShell owns the
  // chrome — this app supplies its name, tile, destinations,
  // and counts, and keeps its route state, search string, and
  // counts plumbing through the shell's props. There is no
  // Settings destination: the shared appearance axes live in
  // the superapp shell's unified Settings (consolidation
  // ruling, 2026-11-13) and arrive as host-provided root
  // attributes; this app has no app-specific settings.
  const onShellNavigate = (key: string) => {
    navigate({ view: key as "overview" | "jobs" | "pings" | "ledger" });
  };

  const jobId = route.view === "job" ? route.jobId : null;
  const inDetail = jobId !== null;
  const activeKey = inDetail ? "jobs" : route.view;

  const crumb = inDetail ? (
    <>
      <button
        type="button"
        onClick={() => navigate({ view: "jobs" })}
        className="flex cursor-pointer items-center gap-[3px] border-0 bg-transparent text-sm font-semibold focus-visible:outline-2 focus-visible:outline-(--wb-focus-ring)"
        style={{ color: "var(--wb-accent)" }}
      >
        <ChevronLeft size={16} />
        Jobs
      </button>
      <span
        className="min-w-0 truncate text-[13.5px]"
        style={{ color: "var(--wb-content-secondary)" }}
      >
        / <b style={{ color: "var(--wb-content-primary)" }}>{jobId}</b>
      </span>
    </>
  ) : (
    <span
      className="text-[13.5px]"
      style={{ color: "var(--wb-content-secondary)" }}
    >
      Scheduler /{" "}
      <b style={{ color: "var(--wb-content-primary)", fontWeight: 650 }}>
        {VIEW_TITLES[route.view]}
      </b>
    </span>
  );

  const searchNode = inDetail ? undefined : (
    <span style={{ width: 210, display: "flex" }}>
      <Input
        type="search"
        ariaLabel={`Search ${VIEW_TITLES[route.view].toLowerCase()}`}
        placeholder={`Search ${VIEW_TITLES[route.view].toLowerCase()}`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{
          backgroundColor: "var(--wb-surface-sunken)",
          borderWidth: 0,
          minHeight: 32,
          fontSize: 13.5,
          width: "100%",
        }}
      />
    </span>
  );

  return (
    <>
      <AppShell
        appName="Scheduler"
        appIcon={<Clock size={19} aria-hidden />}
        appTileStyle={{
          background:
            "linear-gradient(160deg, var(--wb-olive-400), var(--wb-olive-500))",
        }}
        navItems={[
          { key: "overview", label: "Overview" },
          {
            key: "jobs",
            label: "Jobs",
            count: operatorCount,
          },
          {
            key: "pings",
            label: "Pings",
            count: pendingCount,
            hot: pendingCount > 0,
          },
          { key: "ledger", label: "Ledger" },
        ]}
        active={activeKey}
        onNavigate={onShellNavigate}
        onApps={() => setAppsOpen(true)}
        crumb={crumb}
        search={searchNode}
        phoneTitle={jobId ?? undefined}
        phoneBack={
          inDetail
            ? {
                label: "Jobs",
                onClick: () => navigate({ view: "jobs" }),
              }
            : undefined
        }
        style={{ height: "100%" }}
      >
        {route.view === "overview" ? (
          <Overview
            api={api}
            search={search}
            onOpenJob={openJob}
            onOpenJobs={() => navigate({ view: "jobs" })}
          />
        ) : route.view === "jobs" ? (
          <Jobs api={api} search={search} onOpenJob={openJob} />
        ) : route.view === "job" ? (
          <JobDetail
            api={api}
            jobId={route.jobId}
            onBack={() => navigate({ view: "jobs" })}
            onOpenInApp={openInApp}
          />
        ) : route.view === "pings" ? (
          <Pings api={api} search={search} />
        ) : (
          <Ledger api={api} search={search} />
        )}
      </AppShell>

      {appsOpen ? (
        <Sheet open title="Apps" onClose={() => setAppsOpen(false)}>
          <p>
            The Apps back-row returns to the superapp launcher in
            the full Workhorse Superapp shell. This standalone
            preview runs the Scheduler app on its own, so there is
            no launcher to return to here.
          </p>
          <Button variant="primary" onClick={() => setAppsOpen(false)}>
            Stay in Scheduler
          </Button>
        </Sheet>
      ) : null}

    </>
  );
}
