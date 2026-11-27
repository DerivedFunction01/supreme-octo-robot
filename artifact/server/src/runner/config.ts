// The bridge's config seam for the runner (lease panel):
// where the venue panel's API lives. This is the ONLY
// runner module naming the panel's host or port.
// Precedence: VENUE_LEASE_UI_* env — the panel's OWN env
// names (its server reads VENUE_LEASE_UI_HOST /
// VENUE_LEASE_UI_PORT over its config file), fed by the
// privileged hostEnv record (server/src/env.ts) — over
// the loopback defaults below.

export interface BackendAddress {
  host: string;
  port: number;
}

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8793;

export function backendAddress(env: Record<string, string | undefined> = {}): BackendAddress {
  const rawPort = env.VENUE_LEASE_UI_PORT ?? env.COLAB_LEASE_UI_PORT; // step6-retire: COLAB_ dual-read fallback
  const parsed = rawPort ? Number.parseInt(rawPort, 10) : Number.NaN;
  const port = Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : DEFAULT_PORT;
  const host = (env.VENUE_LEASE_UI_HOST ?? env.COLAB_LEASE_UI_HOST)?.trim(); // step6-retire: COLAB_ dual-read fallback
  return { host: host ? host : DEFAULT_HOST, port };
}

export function unreachableMessage(address: BackendAddress): string {
  return (
    `Runner panel unreachable on ${address.host}:${address.port} — ` +
    "is the lease panel running?"
  );
}
