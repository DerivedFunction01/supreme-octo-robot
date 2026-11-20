// The artifact-side settings seam for the workbench
// backend's address — the workbench original's config.ts,
// unchanged in logic. This is the ONLY workbench module
// naming the backend's host or port: precedence is the
// WB_VIEWER_* env (the same names the backend's own seam
// reads) over the defaults below. The env record arrives
// through the privileged hostEnv contract (server/src/
// env.ts) — action code cannot read the host environment
// directly. The client never sees the address at all:
// actions resolve it server-side and hand it to the
// privileged bridge as validated args.

export interface BackendAddress {
  host: string;
  port: number;
}

// Loopback default: the backend binds loopback only. 8792
// is the workbench server's port (8791 is the git repo
// viewer's).
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8792;

export function backendAddress(env: Record<string, string | undefined> = {}): BackendAddress {
  const rawPort = env.WB_VIEWER_PORT;
  const parsed = rawPort ? Number.parseInt(rawPort, 10) : Number.NaN;
  const port = Number.isInteger(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : DEFAULT_PORT;
  const host = env.WB_VIEWER_HOST?.trim();
  return { host: host ? host : DEFAULT_HOST, port };
}

export function unreachableMessage(address: BackendAddress): string {
  return (
    `Workbench server unreachable on ${address.host}:${address.port} — ` +
    "is the workbench server running?"
  );
}
