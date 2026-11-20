// The workbench binding of the shared bridge core
// (server/src/bridge-core.ts): the wbApi / wbRaw contracts,
// the WB_VIEWER_* config seam, and this app's sentences.
// The bridge semantics (status-0 diagnoses, the retry
// policy) live in the core, once, for all four apps.
import type { Ctx } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import {
  type BridgeBinding,
  type BridgeReply,
  type RawReply,
  callRawWith,
  callServerWith,
} from "../bridge-core";
import { backendAddress, unreachableMessage } from "./config";

export type { BridgeReply, RawReply };

const binding: BridgeBinding = {
  contract: privileged.wbApi,
  address: backendAddress,
  unreachableMessage,
  label: "Workbench server",
};

export async function callServer<T>(
  ctx: Ctx,
  path: string,
  method: "GET" | "POST" = "GET",
  body?: unknown,
): Promise<BridgeReply<T>> {
  return callServerWith<T>(ctx, binding, path, method, body);
}

export async function callServerRaw(ctx: Ctx, path: string): Promise<RawReply> {
  return callRawWith(ctx, privileged.wbRaw, backendAddress, path);
}
