// The server-visible env record, obtained per bridge call
// through the privileged hostEnv contract: action code in
// this platform cannot read the host environment directly
// (the build validator forbids it), so the record arrives
// as data from the host side (the step-1 spike's proven
// mechanism). A failed env read resolves to an empty
// record — every config seam then falls back to its
// loopback defaults, which are correct for this host.
import type { Ctx } from "@hatch/space-sdk";
import { privileged } from "@space/privileged";

export async function readServerEnv(ctx: Ctx): Promise<Record<string, string | undefined>> {
  try {
    const res = await ctx.executePrivileged(privileged.hostEnv, {});
    return res.env;
  } catch {
    return {};
  }
}
