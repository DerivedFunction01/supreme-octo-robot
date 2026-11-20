// The honest-failure furniture (AC-1/AC-4): the original
// page's portion() semantics rendered. A surface whose
// backend portion has never loaded is unreachable — it
// says so in the original's words and never presents an
// empty queue as a clear one. A portion failing after a
// load keeps its last good copy, tagged. A source the
// backend reports down is named, with what its absence
// means for the picture.
import type { PortionHealth } from "../attention/types";
import { Group, Row, RowText } from "./groups";

export function UnreachableNotice({ what }: { what: string }) {
  return (
    <Group>
      <Row>
        <RowText
          label={`${what} is unreachable`}
          sub="Nothing is being hidden; this is the whole report."
        />
      </Row>
    </Group>
  );
}

export function StaleNotice({ health }: { health: PortionHealth }) {
  if (health.state !== "stale") return null;
  return (
    <Group>
      <Row>
        <RowText
          label="Showing the last good copy"
          sub="The surface is unreachable right now — polling keeps retrying."
        />
      </Row>
    </Group>
  );
}

/** A server-refused write, stated where every shell view
 * sees it (AC-2): the write's optimistic result has
 * already returned, so the refusal renders here and
 * stands until a later write is accepted. */
export function WriteNotice({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <Group>
      <Row>
        <RowText label="Not saved" sub={text} />
      </Row>
    </Group>
  );
}

export function DownSourcesNotice({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;
  return (
    <Group>
      <Row>
        <RowText
          label={`Source down: ${sources.join(", ")}`}
          sub="Its items may be missing from this picture."
        />
      </Row>
    </Group>
  );
}
