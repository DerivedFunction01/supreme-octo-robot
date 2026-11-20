// The Config group — rendered on a job's detail ONLY when
// the served detail carries a config block (knob-bearing
// entries; contract 09, amendment 2026-11-13). The form is
// the served form: every knob's label, type, unit, value,
// and allowed range come from the adapter's ConfigView —
// this component hardcodes no knob. Saves go through the
// adapter's one writer path with the version the form
// loaded; refusals (stale, out-of-range, constraint) are
// served back and shown whole, with the typed values left
// in place.

import { useState } from "react";
import { Input } from "@workhorse/kit/components/Fields";
import type { SchedulerApi } from "../api";
import type { ConfigView } from "../types";
import { ActionError, ActionRow, Group, GroupLabel } from "./ui";

export function ConfigGroup({
  api,
  jobId,
  config,
}: {
  api: SchedulerApi;
  jobId: string;
  config: ConfigView;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(config.knobs.map((k) => [k.key, String(k.value)])),
  );
  const [loadedVersion, setLoadedVersion] = useState(config.version);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const save = async () => {
    const parsed: Record<string, number> = {};
    for (const knob of config.knobs) {
      // An unparseable field goes to the writer as NaN and
      // is refused there — validation lives at the writer,
      // never re-implemented in the form.
      parsed[knob.key] = Number(values[knob.key]);
    }
    const result = await api.saveConfig(jobId, loadedVersion, parsed);
    if (result.ok) {
      const fresh = api.getJob(jobId)?.config;
      if (fresh) {
        setValues(
          Object.fromEntries(fresh.knobs.map((k) => [k.key, String(k.value)])),
        );
        setLoadedVersion(fresh.version);
      }
      setError(null);
      setNote("Saved — ledgered, and the engine reads it at the next fire.");
    } else {
      setError(result.detail);
      setNote(null);
    }
  };

  return (
    <>
      <GroupLabel>Config</GroupLabel>
      <Group>
        {config.knobs.map((knob) => (
          // Stacked two-line discipline (the owner's row
          // ruling, 2026-11-13): the knob label gets its own
          // full-width line — beside the input it truncated
          // ("Low tier — home free sp…") — and the input +
          // unit ride the line below, with the served range
          // as that line's details text. Neither line
          // truncates (mobile critic, 2026-11-15): at phone
          // width the label still ellipsized ("Topic set
          // register — per-topic allow…") and the range —
          // the parameter being edited — cut mid-number
          // ("1024–1048576 b…"); both wrap whole instead.
          <div
            key={knob.key}
            className="px-3.5 py-[11px]"
            style={{ borderTopColor: "var(--wb-border-default)" }}
          >
            <div
              className="text-[14.5px] font-medium [overflow-wrap:anywhere]"
              style={{ color: "var(--wb-content-primary)" }}
            >
              {knob.label}
            </div>
            <div className="mt-[3px] flex flex-nowrap items-center gap-3">
              <span
                className="min-w-0 flex-1 text-[12.5px] [overflow-wrap:anywhere]"
                style={{ color: "var(--wb-content-secondary)" }}
              >
                {knob.min}–{knob.max} {knob.unit}
              </span>
              <span className="flex flex-none items-center gap-2">
                <Input
                  type="number"
                  ariaLabel={knob.label}
                  value={values[knob.key] ?? ""}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [knob.key]: e.target.value }))
                  }
                  style={{ width: 104, minHeight: 32, fontSize: 13.5 }}
                />
                <span
                  className="text-[12.5px]"
                  style={{ color: "var(--wb-content-secondary)" }}
                >
                  {knob.unit}
                </span>
              </span>
            </div>
          </div>
        ))}
        <ActionRow label="Save config" onClick={save} />
      </Group>
      <ActionError message={error} />
      {note ? (
        <p
          role="status"
          className="mt-2 ml-[2px] text-[13px]"
          style={{ color: "var(--wb-content-secondary)" }}
        >
          {note}
        </p>
      ) : null}
    </>
  );
}
