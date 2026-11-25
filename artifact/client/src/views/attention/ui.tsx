// Shared attention-view chrome: the note toast, the
// confirm dialog, and the refresh cycle — the original's
// globals ($note, confirmDlg, show(view)) stated once as
// a context every attention view consumes, plus the small
// shared marks (presence dot, handler slot dot, band
// headings, scope lines) the views compose identically.

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "@workhorse/kit/components/controls/Button";
import { Sheet } from "@workhorse/kit/components/shell/Sheet";
import { PRESENCE_HUES, slotHue, type PresenceMode } from "./model";

export interface AttentionUi {
  /** The note toast ("Saved", "Presence failed: …"). */
  notify: (message: string) => void;
  /** The original's confirmDlg: a modal with a Keep
   *  button; `onYes` runs only on confirmation. */
  confirm: (text: string, onYes: () => void) => void;
  /** The current view's refresh nonce — portions key
   *  their fetches on it (the original's show(view)
   *  re-render after every action). */
  refreshKey: number;
  /** Re-run the current view's portions. */
  refresh: () => void;
  navigate: (hash: string) => void;
}

const AttentionUiContext = createContext<AttentionUi | null>(null);

export function useAttentionUi(): AttentionUi {
  const ctx = useContext(AttentionUiContext);
  if (!ctx) throw new Error("attention view outside its provider");
  return ctx;
}

export function AttentionProvider({
  navigate,
  children,
}: {
  navigate: (hash: string) => void;
  children: ReactNode;
}) {
  const [note, setNote] = useState<string | null>(null);
  const noteTimer = useRef<number | undefined>(undefined);
  const [confirmState, setConfirmState] = useState<{
    text: string;
    onYes: () => void;
  } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const notify = useCallback((message: string) => {
    setNote(message);
    window.clearTimeout(noteTimer.current);
    noteTimer.current = window.setTimeout(() => setNote(null), 2600);
  }, []);

  const confirm = useCallback((text: string, onYes: () => void) => {
    setConfirmState({ text, onYes });
  }, []);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const ui: AttentionUi = { notify, confirm, refreshKey, refresh, navigate };

  return (
    <AttentionUiContext.Provider value={ui}>
      {children}
      {note ? (
        <div
          role="status"
          className="fixed right-4 bottom-4 left-4 z-50 mx-auto max-w-[420px] px-4 py-3 text-center text-sm font-medium"
          style={{
            backgroundColor: "var(--ui-surface-3)",
            color: "var(--ui-content-primary)",
            borderColor: "var(--ui-border-strong)",
            borderStyle: "solid",
            borderWidth: 1,
            borderRadius: "var(--ui-radius-md)",
            boxShadow: "var(--ui-shadow-overlay)",
          }}
        >
          {note}
        </div>
      ) : null}
      <Sheet
        open={confirmState !== null}
        title="Confirm"
        onClose={() => setConfirmState(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmState(null)}>
              Keep
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                const yes = confirmState?.onYes;
                setConfirmState(null);
                yes?.();
              }}
            >
              Yes
            </Button>
          </>
        }
      >
        <p className="text-sm" style={{ color: "var(--ui-content-primary)" }}>
          {confirmState?.text}
        </p>
      </Sheet>
    </AttentionUiContext.Provider>
  );
}

/* ---------------- shared marks and lines ---------------- */

/** The view's page column: the original's main measure
 *  (max-width 1120, centred) inside the AppShell frame. */
export function PageColumn({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto w-full" style={{ maxWidth: 1120 }}>
      {children}
    </div>
  );
}

/** The view's surface title — the original's h1 TEXT,
 *  no longer a heading element: the route's ONE H1 is
 *  shell-provided (the section name from the view's
 *  crumb, critic M-5/m-2), so the surface's own headline
 *  renders as title text, styled exactly as before. */
export function ViewTitle({ children }: { children: ReactNode }) {
  return (
    <div
      className="text-[28px] font-bold tracking-[-0.01em]"
      style={{ color: "var(--ui-content-primary)", margin: "0 0 4px" }}
    >
      {children}
    </div>
  );
}

/** The scope line under a title (the original's
 *  .scope-line): secondary, small, carries the stale tag. */
export function ScopeLine({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm" style={{ color: "var(--ui-content-secondary)", margin: "0 0 16px" }}>
      {children}
    </p>
  );
}

/** A band heading with its count (the original's
 *  .band-head). */
export function BandHead({ label, count }: { label: string; count?: number }) {
  return (
    <h2
      className="text-[17px] font-semibold"
      style={{ color: "var(--ui-content-primary)", margin: "22px 0 8px" }}
    >
      {label}
      {count !== undefined ? (
        <span style={{ color: "var(--ui-content-muted)", fontWeight: 500 }}> {count}</span>
      ) : null}
    </h2>
  );
}

/** The presence dot (rail/topbar form in the original;
 *  here it rides presence lines inside the views). */
export function PresenceDot({ mode }: { mode: PresenceMode }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block shrink-0 rounded-full"
      style={{ width: 10, height: 10, backgroundColor: PRESENCE_HUES[mode] }}
    />
  );
}

/** A handler's colour-slot dot (the original's .dot-s). */
export function SlotDot({ slot, size = 12 }: { slot: number | undefined; size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, backgroundColor: slotHue(slot) }}
    />
  );
}
