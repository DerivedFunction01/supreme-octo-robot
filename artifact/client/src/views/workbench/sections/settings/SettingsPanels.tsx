// Settings → Workspace panel (repo-home spec §3).
// Workspace is the server's EFFECTIVE configuration,
// READ-ONLY — server config is edited in its config
// file through the seam, never from this UI in v1; the
// panel exists so "what is this instance actually
// running" is answerable in one place.

import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { EffectiveSettingsPayload } from "../../lib/api-types";
import { ErrorWell, SkeletonWell } from "../shared";

const panelTitleStyle: React.CSSProperties = {
  fontSize: "var(--wb-font-size-xs)",
  lineHeight: "var(--wb-line-height-xs)",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--wb-content-secondary)",
  marginTop: "var(--wb-space-32)",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "var(--wb-space-24)",
  padding: "var(--wb-space-8) 0",
  borderBottom: "1px solid var(--wb-border-default)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
  whiteSpace: "nowrap",
};

const valueStyle: React.CSSProperties = {
  color: "var(--wb-content-secondary)",
  fontSize: "var(--wb-font-size-sm)",
  lineHeight: "var(--wb-line-height-sm)",
  textAlign: "right",
  overflowWrap: "anywhere",
};

function fmtValue(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.map(fmtValue).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Row({ label, value, mono }: { label: string; value: unknown; mono?: boolean }) {
  return (
    <div style={rowStyle}>
      <div style={labelStyle}>{label}</div>
      <div style={valueStyle} className={mono ? "mono" : undefined}>
        {fmtValue(value)}
      </div>
    </div>
  );
}

export function SettingsPanels() {
  const query = useQuery({
    queryKey: ["settings-effective"],
    queryFn: () => api.getEffectiveSettings({}),
  });
  if (query.isPending) return <SkeletonWell label="the effective settings" />;
  if (query.isError || !query.data.payload) {
    return (
      <ErrorWell
        section="Settings"
        message={query.data?.error ?? "the companion server did not answer."}
      />
    );
  }
  const settings = query.data.payload as unknown as EffectiveSettingsPayload;
  const config = settings.config;
  const host = config.host;
  const port = config.port;
  return (
    <>
      <h2 style={panelTitleStyle}>Workspace</h2>
      <Row
        label="Server"
        value={host != null && port != null ? `${fmtValue(host)}:${fmtValue(port)}` : null}
        mono
      />
      <Row label="Workspace root" value={config.workspace_root} mono />
      <Row label="Sweep roots" value={config.sweep_roots} mono />
      <Row label="State directory" value={config.state_dir} mono />
      <Row label="Config file" value={settings.config_file} mono />
      <Row label="Config hash" value={settings.config_hash} mono />
      <Row label="File editing" value={config.file_editing_enabled === true ? "on" : "off"} />
    </>
  );
}
