// The attention binding of the shared bridge core
// (server/src/bridge-core.ts): the attentionApi contract,
// the ATTENTION_* config seam, and this app's sentences.
// The bridge semantics (status-0 diagnoses, the retry
// policy) live in the core, once, for all four apps.
import type { Ctx } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";
import { type BridgeBinding, type BridgeReply, callServerWith } from "../bridge-core";
import { backendAddress, unreachableMessage } from "./config";

export type { BridgeReply };

const binding: BridgeBinding = {
  contract: privileged.attentionApi,
  address: backendAddress,
  unreachableMessage,
  label: "Attention server",
};

export async function callServer<T>(
  ctx: Ctx,
  path: string,
  method: "GET" | "POST" = "GET",
  body?: unknown,
): Promise<BridgeReply<T>> {
  return callServerWith<T>(ctx, binding, path, method, body);
}
