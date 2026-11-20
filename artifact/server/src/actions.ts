// The one server of the rebuilt superapp (design §2(a)):
// this module aggregates the four apps' action sets into
// the space's single Actions registry. The sets live in
// per-app modules (./workbench, ./scheduler, ./attention,
// ./runner — each with its actions/bridge/config set, the
// workbench original's file discipline), and the five
// privileged contracts they ride are registered in
// ./privileged.ts. Action names are the apps' own (the
// workbench set carries its original names verbatim); the
// per-app groups are exported alongside the merged
// registry so the shell's relay manifest (client/src/
// relay.ts) can be checked against them action for action.
import type { ActionsModule } from "@hatch/space-sdk";
import { attentionActions } from "./attention/actions";
import { runnerActions } from "./runner/actions";
import { schedulerActions } from "./scheduler/actions";
import { workbenchActions } from "./workbench/actions";

export { attentionActions, runnerActions, schedulerActions, workbenchActions };

export const Actions = {
  ...workbenchActions,
  ...schedulerActions,
  ...attentionActions,
  ...runnerActions,
} satisfies ActionsModule;
