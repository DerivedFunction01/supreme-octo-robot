// Sets a minimal window before any component module loads,
// with matchMedia reporting a match — so the kit's
// useIsPhone seam (<= 480px) engages in the phone harness.
// Imported FIRST by render-harness-phone.tsx.
// @ts-nocheck
const g = globalThis as unknown as { window?: unknown };
g.window = {
  matchMedia: (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
  }),
};
export {};
