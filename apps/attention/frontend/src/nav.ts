import { createContext, useContext } from "react";

export type Route =
  | { name: "glance" }
  | { name: "today" }
  | { name: "handlers" }
  | { name: "handler"; handle: string }
  | { name: "digest" }
  | { name: "rules" }
  | { name: "registries" }
  | { name: "presence" }
  | { name: "night" };

export const NavContext = createContext<{ route: Route; go: (r: Route) => void }>({
  route: { name: "today" },
  go: () => undefined,
});

export function useNav(): { route: Route; go: (r: Route) => void } {
  return useContext(NavContext);
}
