// ---------- Registries (api/1: build_registries) ----------

export interface StatusCodeEntry {
  code: string;
  short: string;
  label: string;
  need: string;
  terminal: boolean;
}

export interface FieldEntry {
  name: string;
  label: string;
  type: string;
  source: string;
  poster_settable: boolean;
}

export interface WaitClassEntry {
  name: string;
  label: string;
  hard_stop: boolean;
}

export interface TemplateEntry {
  kind: string;
  version: number;
  audience: string;
  slots: string[];
  text: string;
}

export interface ItemKindEntry {
  kind: string;
  label: string;
  status_kind: boolean;
  digest_owner: string | null;
  digest_owner_label: string;
}

export interface RegistriesView {
  status_codes: StatusCodeEntry[];
  fields: FieldEntry[];
  wait_classes: WaitClassEntry[];
  operators: { op: string; label: string }[];
  triggers: { on: string; label: string }[];
  actions: { type: string; label: string }[];
  templates: TemplateEntry[];
  item_kinds: ItemKindEntry[];
  handlers: { handle: string; label: string; thread_id: string }[];
}
