// ---------- Vocabulary writes (POST /api/v1/vocab/*) ----------

export type VocabResult = { ok: true } | { ok: false; error: string };

export interface StatusCodeInput {
  code: string;
  short: string;
  label: string;
  need: string;
  terminal: boolean;
}

export interface FieldInput {
  name: string;
  type: string;
}

export interface WaitClassInput {
  name: string;
}

export interface TemplateInput {
  kind: string;
  audience: string;
  slots: string[];
  text: string;
}

export interface ItemKindInput {
  kind: string;
  label: string;
  status_kind: boolean;
  digest_owner: string | null;
}
