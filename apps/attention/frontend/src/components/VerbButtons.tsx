// The served-verb button row: every steering surface
// (handler status card, steering group, digest topic
// lanes) renders the same row over the served verb set.
import type { VerbEntry } from "../attention/types";
import { Button } from "@workhorse/kit/components/Button";

export function VerbButtons({
  verbs,
  onAct,
}: {
  verbs: VerbEntry[];
  onAct: (verb: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {verbs.map((v) => (
        <Button key={v.verb} variant="secondary" onClick={() => onAct(v.verb)}>
          {v.label}
        </Button>
      ))}
    </div>
  );
}
