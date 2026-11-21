// Control exercise harness (split from exercise-ui.tsx):
// the jsdom host, the global shims the kit's components
// need, the one real React copy, and the DOM driver
// helpers every exercise phase drives the app through.
// Importing this module performs the setup; the phases
// (exercise-ui.tsx's desktop frames, exercise-phone.ts)
// import the prepared host from here.
import { JSDOM } from "jsdom";
const dom = new JSDOM(
  "<!doctype html><html><body><div id=\"root\"></div></body></html>",
  { url: "http://127.0.0.1:5417/", pretendToBeVisual: true },
);
export const { window } = dom;
const g = globalThis as Record<string, unknown>;
const setGlobal = (key: string, value: unknown) =>
  Object.defineProperty(g, key, {
    value,
    configurable: true,
    writable: true,
  });
setGlobal("window", window);
setGlobal("document", window.document);
setGlobal("navigator", window.navigator);
setGlobal("HTMLElement", window.HTMLElement);
setGlobal("HTMLInputElement", window.HTMLInputElement);
setGlobal("Element", window.Element);
setGlobal("Node", window.Node);
setGlobal("MouseEvent", window.MouseEvent);
setGlobal("KeyboardEvent", window.KeyboardEvent);
setGlobal("Event", window.Event);
setGlobal("IS_REACT_ACT_ENVIRONMENT", true);
window.matchMedia = (query: string) =>
  ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    onchange: null,
  }) as MediaQueryList;

export const React = await import("react");
// The kit's components are transformed by tsx under their home
// tsconfig's JSX mode, which references a free `React` identifier;
// provide it from the one real react copy.
setGlobal("React", React);
export const { act } = React;
export const { createRoot } = await import("react-dom/client");
export const { Preview } = await import("../src/Preview");
export const { mockApi } = await import("../src/mock/mock-adapter");
export const { Row, OutcomeChip, jobChip } = await import("../src/components/ui");

let failures = 0;
let checks = 0;
export function check(label: string, cond: boolean, extra?: string) {
  checks++;
  if (!cond) failures++;
  console.log(
    `${cond ? "PASS" : "FAIL"}  ${label}${extra ? ` — ${extra}` : ""}`,
  );
}

export const sleep = (ms: number) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

export const bodyText = () => window.document.body.textContent ?? "";

export function buttons(): HTMLButtonElement[] {
  return [...window.document.querySelectorAll("button")] as HTMLButtonElement[];
}

function clickButton(text: string, opts: { exact?: boolean } = {}): boolean {
  const btn = buttons().find((b) =>
    opts.exact
      ? (b.textContent ?? "").trim() === text
      : (b.textContent ?? "").includes(text),
  );
  if (!btn) return false;
  btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  return true;
}

export async function click(text: string, opts: { exact?: boolean } = {}) {
  let ok = false;
  await act(async () => {
    ok = clickButton(text, opts);
  });
  return ok;
}

export async function clickRadio(value: string) {
  let ok = false;
  await act(async () => {
    const input = window.document.querySelector(
      `input[type="radio"][value="${value}"]`,
    ) as HTMLInputElement | null;
    if (input) {
      input.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
      ok = true;
    }
  });
  return ok;
}

export async function setSearch(value: string) {
  await act(async () => {
    const input = window.document.querySelector(
      'input[type="search"]',
    ) as HTMLInputElement | null;
    if (!input) return;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )!.set!;
    setter.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

export async function setInputByLabel(label: string, value: string) {
  await act(async () => {
    const input = window.document.querySelector(
      `input[aria-label="${label}"]`,
    ) as HTMLInputElement | null;
    if (!input) return;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )!.set!;
    setter.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

export function inputValueByLabel(label: string): string | null {
  const input = window.document.querySelector(
    `input[aria-label="${label}"]`,
  ) as HTMLInputElement | null;
  return input ? input.value : null;
}

export async function waitFor(label: string, pred: () => boolean, timeoutMs = 9000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (pred()) return true;
    await sleep(400);
  }
  console.log(`  (timed out waiting: ${label})`);
  return false;
}

/** The exercise's tallies, read by the entry at the end
 *  of the last phase. */
export function results(): { checks: number; failures: number } {
  return { checks, failures };
}
