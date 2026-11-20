// The bridge's config seam for the scheduler backend: where
// the scheduler server's API lives. This is the ONLY
// scheduler module naming the backend's host or port.
// Precedence: SCHEDULER_API_* env (the scheduler original's
// seam names, fed by the privileged hostEnv record — see
// server/src/env.ts) over the loopback defaults below.

export interface BackendAddress {
  host: string;
  port: number;
}

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8796;

export function backendAddress(env: Record<string, string | undefined> = {}): BackendAddress {
  const rawPort = env.SCHEDULER_API_PORT;
  const parsed = rawPort ? Number.parseInt(rawPort, 10) : Number.NaN;
  const port = Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : DEFAULT_PORT;
  const host = env.SCHEDULER_API_HOST?.trim();
  return { host: host ? host : DEFAULT_HOST, port };
}

export function unreachableMessage(address: BackendAddress): string {
  return (
    `Scheduler server unreachable on ${address.host}:${address.port} — ` +
    "is the scheduler server running?"
  );
}
