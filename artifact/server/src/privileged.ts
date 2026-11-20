// Privileged host handlers — the one bridge module of the
// rebuilt superapp (design §2(a)): it registers the five
// backend contracts (wbApi, wbRaw, schedulerApi,
// attentionApi, runnerApi) plus the hostEnv contract that
// feeds the per-app config seams.
//
// The transport is the workbench original's, verbatim in
// shape: a raw node:net socket HTTP request to the app's
// loopback backend. The hosting daemon's egress proxy
// breaks loopback fetch, so every call travels this socket
// path, never fetch. Host/port/method/path/body are
// validated args supplied by the actions from the per-app
// config seams (server/src/<app>/config.ts); this module
// hardcodes no target. The four JSON contracts share one
// shape (the workbench dialect the rebuild normalizes on);
// wbRaw is its raw-bytes sibling, carrying the body as
// base64 so exact bytes ride the bridge.
import { connect } from "node:net";
import { definePrivilegedContracts, definePrivilegedHandlers, z } from "@hatch/space-sdk";

const TIMEOUT_MS = 12000;

interface SocketResult {
  status: number;
  json: unknown;
}

function fetchJson(args: {
  host: string;
  port: number;
  method: string;
  path: string;
  body?: string | null;
}): Promise<SocketResult> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value: SocketResult) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    const socket = connect(args.port, args.host);
    socket.setTimeout(TIMEOUT_MS);
    const chunks: Buffer[] = [];
    socket.on("connect", () => {
      const body = args.body ?? "";
      let request =
        `${args.method} ${args.path} HTTP/1.1\r\n` +
        `Host: ${args.host}:${args.port}\r\n` +
        "Accept: application/json\r\nConnection: close\r\n";
      if (args.method === "POST") {
        request += `Content-Type: application/json\r\nContent-Length: ${Buffer.byteLength(body)}\r\n`;
      }
      request += "\r\n";
      if (args.method === "POST") request += body;
      socket.write(request);
    });
    socket.on("data", (chunk: Buffer) => chunks.push(chunk));
    socket.on("timeout", () => {
      socket.destroy();
      done({ status: 0, json: { error: `timed out after ${TIMEOUT_MS}ms` } });
    });
    socket.on("error", (err) => {
      done({ status: 0, json: { error: err.message } });
    });
    socket.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const splitAt = raw.indexOf("\r\n\r\n");
      if (splitAt === -1) {
        done({ status: 0, json: { error: "malformed HTTP response" } });
        return;
      }
      const head = raw.slice(0, splitAt);
      const match = /^HTTP\/1\.[01] (\d{3})/.exec(head);
      const status = match ? Number(match[1]) : 0;
      let body = raw.slice(splitAt + 4);
      if (/transfer-encoding:\s*chunked/i.test(head)) body = dechunk(body);
      let json: unknown = null;
      try {
        json = JSON.parse(body) as unknown;
      } catch {
        json = null;
      }
      done({ status, json });
    });
  });
}

function dechunk(body: string): string {
  let out = "";
  let rest = body;
  for (;;) {
    const end = rest.indexOf("\r\n");
    if (end === -1) return out;
    const size = Number.parseInt(rest.slice(0, end), 16);
    if (!Number.isFinite(size) || size <= 0) return out;
    out += rest.slice(end + 2, end + 2 + size);
    rest = rest.slice(end + 2 + size + 2);
  }
}

interface RawResult {
  status: number;
  contentType: string | null;
  bodyBase64: string;
}

// The raw-bytes sibling of fetchJson: the same socket
// discipline, but the body is carried as base64 instead of
// being JSON-parsed, so an entry page's exact bytes can
// ride the bridge to the render action. A failed socket
// reports status 0 with an empty body; the caller reads
// that as unreachable, never as an empty file.
function fetchRaw(args: {
  host: string;
  port: number;
  method: string;
  path: string;
  body?: string | null;
}): Promise<RawResult> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value: RawResult) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    const failed = { status: 0, contentType: null, bodyBase64: "" };
    const socket = connect(args.port, args.host);
    socket.setTimeout(TIMEOUT_MS);
    const chunks: Buffer[] = [];
    socket.on("connect", () => {
      const body = args.body ?? "";
      let request =
        `${args.method} ${args.path} HTTP/1.1\r\n` +
        `Host: ${args.host}:${args.port}\r\n` +
        "Accept: */*\r\nConnection: close\r\n";
      if (args.method === "POST") {
        request += `Content-Type: application/json\r\nContent-Length: ${Buffer.byteLength(body)}\r\n`;
      }
      request += "\r\n";
      if (args.method === "POST") request += body;
      socket.write(request);
    });
    socket.on("data", (chunk: Buffer) => chunks.push(chunk));
    socket.on("timeout", () => {
      socket.destroy();
      done(failed);
    });
    socket.on("error", () => {
      done(failed);
    });
    socket.on("end", () => {
      const raw = Buffer.concat(chunks);
      const splitAt = raw.indexOf("\r\n\r\n");
      if (splitAt === -1) {
        done(failed);
        return;
      }
      const head = raw.subarray(0, splitAt).toString("utf8");
      const match = /^HTTP\/1\.[01] (\d{3})/.exec(head);
      const status = match ? Number(match[1]) : 0;
      const typeMatch = /^content-type:\s*(.+)$/im.exec(head);
      const contentType = typeMatch?.[1] ? typeMatch[1].trim() : null;
      let body = raw.subarray(splitAt + 4);
      if (/transfer-encoding:\s*chunked/i.test(head)) body = dechunkBuffer(body);
      done({ status, contentType, bodyBase64: body.toString("base64") });
    });
  });
}

function dechunkBuffer(body: Buffer): Buffer {
  const parts: Buffer[] = [];
  let rest = body;
  for (;;) {
    const end = rest.indexOf("\r\n");
    if (end === -1) break;
    const size = Number.parseInt(rest.subarray(0, end).toString("utf8"), 16);
    if (!Number.isFinite(size) || size <= 0) break;
    parts.push(rest.subarray(end + 2, end + 2 + size));
    rest = rest.subarray(end + 2 + size + 2);
  }
  return Buffer.concat(parts);
}

// The four JSON contracts share one shape (the workbench
// dialect): validated target + method + path + optional
// body in, HTTP status + parsed JSON out. Status 0 is the
// transport failure shape (the socket never got an answer)
// and is never conflated with a server state by the
// bridges. The shape is written out per contract, as the
// originals wrote it — the builder's contract extraction
// (server/.generated/) takes this object verbatim.
export const privileged = definePrivilegedContracts({
  wbApi: {
    request: z.object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535),
      method: z.enum(["GET", "POST"]).default("GET"),
      path: z.string(),
      body: z.string().nullable().optional(),
    }),
    response: z.object({ status: z.number(), json: z.unknown() }),
    capabilities: ["network.loopback"],
    timeoutMs: 20000,
  },
  wbRaw: {
    request: z.object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535),
      method: z.enum(["GET", "POST"]).default("GET"),
      path: z.string(),
      body: z.string().nullable().optional(),
    }),
    response: z.object({
      status: z.number(),
      contentType: z.string().nullable(),
      bodyBase64: z.string(),
    }),
    capabilities: ["network.loopback"],
    timeoutMs: 20000,
  },
  schedulerApi: {
    request: z.object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535),
      method: z.enum(["GET", "POST"]).default("GET"),
      path: z.string(),
      body: z.string().nullable().optional(),
    }),
    response: z.object({ status: z.number(), json: z.unknown() }),
    capabilities: ["network.loopback"],
    timeoutMs: 20000,
  },
  attentionApi: {
    request: z.object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535),
      method: z.enum(["GET", "POST"]).default("GET"),
      path: z.string(),
      body: z.string().nullable().optional(),
    }),
    response: z.object({ status: z.number(), json: z.unknown() }),
    capabilities: ["network.loopback"],
    timeoutMs: 20000,
  },
  runnerApi: {
    request: z.object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535),
      method: z.enum(["GET", "POST"]).default("GET"),
      path: z.string(),
      body: z.string().nullable().optional(),
    }),
    response: z.object({ status: z.number(), json: z.unknown() }),
    capabilities: ["network.loopback"],
    timeoutMs: 20000,
  },
  // The env seam: action code cannot read the host
  // environment (the platform validator forbids it), so
  // the server-visible env record — only the eight names
  // the four apps' config seams consume — is read here, on
  // the host side, and handed to the actions as data (the
  // step-1 spike's proven mechanism). With no env set, the
  // seams resolve their loopback defaults, which the spike
  // proved reach the real backends.
  hostEnv: {
    request: z.object({}),
    response: z.object({ env: z.record(z.string(), z.string()) }),
    capabilities: [],
    timeoutMs: 5000,
  },
});

// The config-seam env names, one pair per app — the same
// names each backend's own seam reads (design §1):
// workbench WB_VIEWER_*, scheduler SCHEDULER_API_*,
// attention ATTENTION_*, runner COLAB_LEASE_UI_*.
export const ENV_KEYS = [
  "WB_VIEWER_HOST",
  "WB_VIEWER_PORT",
  "SCHEDULER_API_HOST",
  "SCHEDULER_API_PORT",
  "ATTENTION_HOST",
  "ATTENTION_PORT",
  "COLAB_LEASE_UI_HOST",
  "COLAB_LEASE_UI_PORT",
] as const;

function socketCall(args: {
  host: string;
  port: number;
  method?: string;
  path: string;
  body?: string | null;
}): Promise<SocketResult> {
  return fetchJson({
    host: args.host,
    port: args.port,
    method: args.method ?? "GET",
    path: args.path,
    body: args.body ?? null,
  });
}

export const privilegedHandlers = definePrivilegedHandlers(privileged, {
  async wbApi(args) {
    return socketCall(args);
  },
  async wbRaw(args) {
    return fetchRaw({
      host: args.host,
      port: args.port,
      method: args.method ?? "GET",
      path: args.path,
      body: args.body ?? null,
    });
  },
  async schedulerApi(args) {
    return socketCall(args);
  },
  async attentionApi(args) {
    return socketCall(args);
  },
  async runnerApi(args) {
    return socketCall(args);
  },
  async hostEnv() {
    const env: Record<string, string> = {};
    for (const key of ENV_KEYS) {
      const value = process.env[key];
      if (value !== undefined) env[key] = value;
    }
    return { env };
  },
});
