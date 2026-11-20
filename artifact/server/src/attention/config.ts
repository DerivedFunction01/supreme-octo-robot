// The bridge's config seam for the attention backend:
// where the attention server's API lives. This is the ONLY
// attention module naming the backend's host or port.
// Precedence: ATTENTION_* env — the attention backend's
// OWN env names (its settings seam reads ATTENTION_HOST /
// ATTENTION_PORT), fed by the privileged hostEnv record
// (server/src/env.ts) — over the loopback defaults below.

export interface BackendAddress {
  host: string;
  port: number;
}

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8797;

export function backendAddress(env: Record<string, string | undefined> = {}): BackendAddress {
  const rawPort = env.ATTENTION_PORT;
  const parsed = rawPort ? Number.parseInt(rawPort, 10) : Number.NaN;
  const port = Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : DEFAULT_PORT;
  const host = env.ATTENTION_HOST?.trim();
  return { host: host ? host : DEFAULT_HOST, port };
}

export function unreachableMessage(address: BackendAddress): string {
  return (
    `Attention server unreachable on ${address.host}:${address.port} — ` +
    "is the attention server running?"
  );
}
