// The published (integration) entry: the same App the
// preview mounts, over the LIVE venue surface — the data
// seam selects the live adapter here, the scheduler
// integration entry's shape. The live base is the serving
// origin, full stop: the surface that serves the app
// serves its /api/* on the same origin, and no query
// parameter names another base. (The ?api= override this
// entry used to honour was removed as a HIGH security
// finding, 2026-11-16: nothing in the shell, the embed
// harness, or the rigs set it, and a crafted link could
// have pointed the adapter's lease/access POSTs — which
// carry session identifiers — at an arbitrary base.)
// ?adapter=mock keeps the mock for harness checks. The
// standalone preview (main.tsx) stays on the mock
// adapter — that is its purpose.

const params = new URLSearchParams(window.location.search);
globalThis.__RUNNER_EMBEDDED__ = true;
if (params.get("adapter") !== "mock") {
  globalThis.__RUNNER_LIVE__ = { baseUrl: "" };
}

// The globals above are set synchronously during this
// module's evaluation; the dynamic import's module graph
// (which reads them at the seam) evaluates after.
void import("./embedded");

export {};
