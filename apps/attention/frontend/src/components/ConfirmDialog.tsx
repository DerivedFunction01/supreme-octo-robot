// A confirm gate for the taps that reach further than the
// item itself — the original frontend's confirm() calls,
// rendered as a kit sheet: muting a type holds every open
// item of that type from the handler, and a done that does
// not clear at the source leaves the source's copy
// standing. The message is the caller's served text; the
// dialog itself carries no copy of its own.
import { Button } from "@workhorse/kit/components/Button";
import { Sheet } from "@workhorse/kit/components/Sheet";

export function ConfirmDialog({
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  message: string | null;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Sheet
      open={message !== null}
      title="Confirm"
      onClose={onCancel}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm">{message}</p>
    </Sheet>
  );
}
