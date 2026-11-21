// The Code section's selected checkout (SPEC §21): the
// canonical project id addresses the project; this
// context carries which of its checkouts the surface
// is reading — undefined for the main checkout, else
// the linked worktree's census id. Code.tsx owns the
// selection state and provides it; the tab components
// read it here instead of threading it through every
// prop list.

import { createContext, useContext } from "react";

export const CheckoutContext = createContext<string | undefined>(undefined);

export function useCheckout(): string | undefined {
  return useContext(CheckoutContext);
}
