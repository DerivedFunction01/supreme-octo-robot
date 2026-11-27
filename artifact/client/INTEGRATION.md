# One client — integration contracts

The composition contract for the workhorse superapp's single
integrated frontend (owner ruling;
audit Addendum 3). **One app: one client, one bundle
(§1), one router, the four apps
as views on the unified kit.** No
iframes, no postMessage relay, no per-app bundles, shells,
or kits — the one sanctioned iframe is the entry preview's
(§11.7). The frame shell this replaced is deleted; do not
rebuild any part of it.

References of record: the kit at repo-root
`kit/` (its README is the consumption rule) and the view
trees under `client/src/views/<app>/` (behaviour and
screens of record).

## 1. Shape

- Entry: `client/index.html` → `src/main.tsx` → `src/App.tsx`.
  `build.mjs` runs the SDK's canonical `buildClient()`
  form with a shape guard: the staging must contain
  exactly ONE document (`dist/index.html`) and exactly
  ONE JS bundle carrying the shell, the Launcher, and
  every view (the mount seam's dynamic imports inlined);
  a split build fails the guard, because the platform's
  CVM publish stage accepts exactly one JS bundle (the
  per-view split retired). Each view's
  shell-facing half (nav, active key, search declaration,
  crumb — the H1/title source) lives in
  `views/<app>/meta.ts` and is imported statically, so
  the chrome is complete from the first paint; the
  view's component tree joins the one bundle through
  the mount seam,
  mounted in the kit `SectionBoundary` — a chunk in
  flight shows the kit `EmptyState` pending form, and a
  failed chunk lands in the boundary's error form inside
  intact chrome, never a blank root.
- The shell (App.tsx) owns: the route, the appearance
  state, the presence state, per-app nav badges, and the
  chrome. It holds **no app data and no transport**.
- Views own their data, fetched through the single action
  layer (§3) with react-query (`spaceQueryClient` is
  provided above App; do not create a second client).

## 2. Routing and view mounts

Route values (`src/lib/router.tsx`): the route is shell
state, never the document URL — no navigation path
mutates `window.location` (the desktop viewer blocks
fragment navigation on its blob: document; desktop
click probe, Step 4). The values keep the hash grammar
below: the first segment names the app; the remainder
is the app's **subroute**, handed to its mount verbatim,
always beginning with `/`.

| Hash | Mount |
|---|---|
| `#/` | Launcher (shell view) |
| `#/settings` | Settings (shell view, §5–§6) |
| `#/workbench[/<subroute>]` | `src/views/workbench/` |
| `#/scheduler[/<subroute>]` | `src/views/scheduler/` |
| `#/attention[/<subroute>]` | `src/views/attention/` |
| `#/runner[/<subroute>]` | `src/views/runner/` |

Unknown hashes land on the Launcher, never a blank.

Each mount is one module exporting an `AppViewModule`
(`src/lib/view-contract.ts` is the code form):

- `nav` — sidebar destinations in order (`key`, `label`,
  `href`); the key is the badge key and active-key space.
- `activeKey(subroute)` — the nav key for a subroute
  (`""` when none).
- `crumb(subroute)` — TopBar breadcrumb segments, app
  name first.
- `searchPlaceholder(subroute)` — optional: the TopBar
  search slot's placeholder for a subroute, or
  `undefined` where that surface has no search
  behaviour (the slot then renders nothing — §11.5).
  Modules that do not declare it keep the per-app
  default (§11.5).
- `Component` — receives `ViewProps`: `subroute`,
  `navigate(hash)` (any full hash in the client —
  cross-app navigation is ordinary navigation; there is
  no message bus), and `onBadges(badges)` (live nav
  counts keyed by nav key; `hot: true` renders the
  vermilion badge).

Subroute grammars (each lane's inventory of record):

- **Workbench** — its route table
  (`views/workbench/lib/routing.ts`) read against the
  remainder: `/` home · `/projects` chooser ·
  `/board` · `/repos[/<id>]` (id may contain slashes) ·
  `/p/<slug>/<section>[/<item>]` with section ∈ overview |
  entries | plans | todos | board (retired
  mockups/artifacts segments map to entries at parse
  time) · `/p/<slug>/preview/<entryId>` — one entry's
  page as a full page of the client (FU-1, §11.7): the
  drill-in's door navigates here, the page's own top bar
  (back to the drill-in, the entry's title, an info
  action opening the kit Sheet with the record's fields)
  rides above the page, and the mount renders the route
  full-bleed, outside the centred column · `/settings`
  (the app's OWN settings view, workbench storyboard
  frame 9 — distinct from the shell's unified
  `#/settings`).
- **Scheduler** — `/` Overview · `/jobs` · `/jobs/<id>` ·
  `/pings` · `/ledger` (the view inventory in
  `views/scheduler/`).
- **Attention** — `/` Today · `/digest` · `/handlers` ·
  `/handlers/<handle>` · `/rules` · `/registries`.
  Presence and Digest settings are NOT routes (§6).
  The digest's topic disclosures are mount-on-demand:
  a closed topic renders no lane DOM (the
  ReposTrackingPanel form), so closed-state geometry
  carries no hidden boxes (critic N-2).
- **Runner** — `/` Leases · `/leases/<id>` · `/new` ·
  `/access` · `/budget` · `/events` · `/orphans`.

Hash segments arrive URL-encoded; decode per segment, as
the originals did. Build hrefs with the full hash
(`#/scheduler/jobs/<enc(id)>`); inside the workbench,
its restored href builders produce its own `#/…` forms —
prefix them with `/workbench` at the seam.

Titling (the shell's contract; critic M-5):
the shell renders exactly one `<h1>` per route, inside
the route's one `<main>`, and `document.title` follows
the same name as `<Section> · <App>` (the Launcher's
title is the app name alone; unified Settings is
`Settings · Workhorse Superapp`). The name's source is
the view module's `crumb(subroute)`: segment 2 — except
on workbench project routes (`/p/…`), where segment 2
is the project slug (a detail id; the breadcrumb
carries it as path) and the shell takes segment 3, the
section. On phone the shell H1 is `sr-only`: the
PhoneShell large title presents the same name. Views
render no page-level `<h1>` of their own; a route
outside AppShell (the unified Settings) carries its
own one H1 as the route's H1. A view renders no
visible title repeating the shell H1's section name:
display titles in a view name the item in view (a
repo's name, an entry's title), never the section
(critic M-5 cure).

Phone presentation (critic M-3): every phone route
presents as a pushed screen from the first render — the
shell passes `phoneBack`/`phoneTitle` so the view
mounts, and fires its actions, on cold arrival, with
content directly under the back row. The section menu
is back-row navigation, never a gate: it opens from
the back row and closes on any selection or route
change.

## 3. The single action layer

`src/lib/actions.ts` is the ONLY transport a view may
import:

```ts
import { api, type ApiResponse } from "../../lib/actions";
```

One `createActionClient` typed over the merged server
registry (`server/src/actions.ts` — the four apps' sets
spread flat; the per-app groups are exported there too:
`workbenchActions`, `schedulerActions`, `attentionActions`,
`runnerActions`). No per-app clients, no fetch wrappers,
no relay, no second client anywhere in `src/`.

Response semantics (the server sets' own contracts,
typed per action — consume the type, never a hand-rolled
shape): the scheduler/attention/runner sets return the
common envelope `{status, payload, error}` — `status 0`
is a transport failure (bridge down) with the diagnosis
in `error`, distinct from any server state; a backend
body with a string `error` is lifted to `envelope.error`
with `payload: null`; otherwise `payload` is the backend
JSON verbatim. The workbench set is its original's thin
proxy: payload verbatim, status riding along, an
unreachable backend returning in the same envelope
shape, never a hang or a throw. Bridge-down handling
keeps the originals' semantics: last-good stays rendered
at read time in the view; status 0 is never rendered as
data. Per-app call mappings live in each view's model
module (scheduler: `views/scheduler/model.ts` —
positional args become named fields: `getJob({jobId})`,
`getLedger({limit})`).

## 4. Kit consumption

The kit's one home is repo-root `kit/` (package
`@workhorse/kit`). Consume it from there — **never copy
kit files into the client**.

- Imports: `@workhorse/kit/components/<Name>` and
  `@workhorse/kit/lib/responsive` — the kit is a
  declared dependency of the artifact package
  (`"@workhorse/kit": "file:../kit"` in
  `artifact/package.json`), so tsc and the bundler
  resolve the specifier through `artifact/node_modules`
  (bun install materializes the kit there from its
  home). No tsconfig path aliases point at the kit.
  The kit's components import only React (and `katex`,
  the kit's one declared dependency).
- Component inventory as consumed by the shell:
  `AppShell` (with `SidebarNav`/`TopBar`/`PhoneShell`
  presentations), `GroupedList` + `GroupLabel`/`Row`/
  `StatRow`/`SwitchRow`/`RadioRow`/`NoticeRow`/
  `ActionRow`, `Card`, `SegmentedControl`,
  `PaletteSelect`, `ModeControl`, `DensityToggle`,
  `Input`/`Select`/`Field` (Fields.tsx), `Badge`, `Chip`,
  `StatusChip`, `DataTable`, `DegradedBanner`,
  `EmptyState`, `Toggle`, `Checkbox`/`Radio`, `LogRow`,
  `Sheet`, `ArmConfirm`, `AnnotationBadge`, `TriageRow`,
  `Lane`, `Frame`, `Specimen` (review harness, not a
  surface), `Math`, `SectionBoundary`, `Tooltip`,
  `StateControls`. A surface needing more extends the
  kit once, in its home — never locally.
- `LogRow` clamps an overflowing headline in place: a
  headline beyond the payload budget
  (`LOG_PAYLOAD_MAX_LINES = 3` lines or
  `LOG_PAYLOAD_MAX_CHARS = 300` chars, `kit/lib/log-payload.ts`,
  a pure predicate over the served text — never a DOM
  measurement) renders clamped with a "Show full payload"
  toggle that expands it in place to the full headline
  verbatim and collapses on a second tap. Rows inside the
  budget render exactly as before, with no toggle. On
  interactive rows the toggle is its own control beside
  the row's open button, never nested inside it.
- CSS: the client's `src/index.css` carries Tailwind, the
  SDK styles, and the `@source` lines for the kit's
  `components/` and `lib/` (the kit README's rule —
  without them, kit-only utilities silently never
  generate). The kit's theme distribution is imported
  in `src/main.tsx` as its own stylesheet root
  (`@workhorse/kit/themes/index.css`): as a root, its
  `fonts.css` url()s resolve against the kit's home and
  the bundler inlines the woff2 (Inter, IBM Plex Mono)
  as data URIs; inlined through another file's @import
  chain they resolve against the wrong directory and
  the build fails. `main.tsx` likewise imports
  `@workhorse/kit/themes/highlight.css` as its own root.
- Build-facing form: none. The kit's externals (react;
  katex; tailwindcss, imported by its themes entry)
  resolve by walking up from the kit's installed
  location into the artifact's own node_modules — the
  dependency declaration above is the whole mechanism,
  and `client/build.mjs` carries no resolution
  scaffolding. Nothing creates a repo-root
  `node_modules`, and a clean checkout verifies end to
  end with `bun run verify:client` (§10).
- AppShell composition rule (kit README): views that do
  NOT self-pad take `AppShell` whole (its frame insets
  the content — the shell does this); a view that
  self-pads (the workbench's full-bleed sections)
  composes the kit's exported `SidebarNav` + `TopBar`
  with an unpadded content column instead. Never both.

## 5. Appearance contract

One state, shell-owned (`src/lib/appearance.ts`), applied
once at the document root, persisted in localStorage
under `workhorse.appearance`:

| Axis | Values | Default | Root attribute |
|---|---|---|---|
| Palette | olive, teal | olive | `data-palette` (always set) |
| Mode | system, light, dark | system | `data-mode` (absent = system) |
| Density | comfortable, compact | comfortable | `data-density` (always set) |

The kit themes select on exactly these attributes
(`[data-palette="olive"]`, `[data-mode="dark"]`,
`[data-density="compact"]`). Applied before first paint
in main.tsx. Changed only in the unified Settings view
(`#/settings`), through the kit's own `ModeControl` /
`PaletteSelect` / `DensityToggle`. No view sets these
attributes, and no per-app appearance state exists.

The kit's contrast gate (its `tools/verify-contrast`)
holds every content voice, the muted voice included,
to the 4.5:1 bar on every palette × mode surface
pairing (critic B-2); each palette's muted
token sits on its own muted→secondary scale. The gate
also proves status text on its own tints — Chip,
StatusChip, Badge, Lane, and the color-mix badges
(critic N-1): the badge mix constants (a
16% tint background; the foreground as a 43% hue step
toward the content colour, in `LogRow`'s KindBadge
and `AppShell`'s CountBadge) are mirrored as data in
the gate, and a component that changes its mix owes
the gate the same change. The gate also proves text
on solid fills (its Part 4): the `notify` /
`on-notify` token pair — the one solid accent badge
colour, a deepened vermilion held to the same bar —
and the Button rest-state on-accent pairs; a solid
fill that carries text reads a token pair the gate
proves, never a raw primitive.

The shell wrapper's backdrop and inherited chrome
colour follow the client's own appearance, never the
host colour scheme: `index.css` binds the wrapper's
`--bg` / `--text` hooks to the kit's canvas and
primary content tokens and keys `color-scheme` on
`[data-mode]`, so a runtime Light/Dark switch
re-themes the whole surface — chrome included — with
no reload (critic confirmation F-1). A
kit control's focus indicator must contrast with the
control's own filled state, not only with the page:
where a checked fill is the accent itself, the
indicator is an inset separator in the on-accent
token (the Toggle rule; confirmation F-3). The same
rule shapes the Checkbox (its separator is the
fill's own on-colour). Button state mixes step
toward the per-mode `press-shade` token — black in
light modes, white in dark modes, where the text is
near-black and a step toward black would spend the
contrast it must create; the gate's Part 5 mirrors
the Button state matrix as data, mixes included
(confirmation F9b).

## 6. Presence, the Launcher widget, and Settings sections

Presence is attention's served state, surfaced by the
shell in three places, all bound to ONE shell-held state
(App.tsx), which is the served state (the binding
below):

- the TopBar chips slot: `shell/PresenceControl.tsx`
  (the kit SegmentedControl form: Active / Focus / Away)
  on every app view;
- the Launcher's Today widget: the presence line plus
  the decision line — `Launcher` takes `attentionCount`,
  `presenceExpiresAt`, and `nextDigestLabel` props, all
  fed from the shell's served state: the count is the
  glance's `decision_count` (the attention mount's
  reported `today` nav badge is the fallback), and the
  presence line ends `· until <time>` when the served
  presence carries an expiry;
- Settings: `views/attention/settings-sections.tsx`
  exports `PresenceSection` (attention storyboard
  frame 4) and `DigestSection` (frame 5), mounted by
  `shell/Settings.tsx` under the Presence and Attention
  groups. The sections are served-state-driven: the
  presence state half shares the shell state, and the
  Expires group represents the served expiry itself —
  when the served expiry matches no preset it renders
  as a checked **Current** choice carrying the served
  instant, and selecting it (or changing mode while it
  stands) posts the served instant back, never a clear
  (critic M-6); the presets (In 1 hour / At 5:00 PM /
  Tomorrow, 8:00 AM / No expiry) remain as change
  options. The digest switches bind the same way. The
  Expires group is served-state gated: until the
  shell's served presence has landed and agrees with
  the section's own glance, the group renders one
  non-postable honest line in place of the radio
  groups — a failed glance read can never become a
  postable "No expiry"; the shell hook retries the
  glance until it lands and refuses presence posts
  while never-loaded (critic M-6 cure).

**Binding:** read via the merged registry's
`getGlance` — `useServedPresence`
(`views/attention/presence.ts`) exposes the presence,
its expiry, and `decisionCount`; write presence via
`postPresence` and digest prefs via `postDigestPrefs`.
The shell state IS the served state (with its expiry);
the Launcher widget takes its count and next-window
label from the glance; the sections' local halves are
retired. Frame 4's expiry options carry the frame's
instance labels ("At 5:00 PM", "Tomorrow, 8:00 AM") —
the concrete times compute at render.

## 7. View-file layout

```
client/src/
  main.tsx            boot (appearance pre-paint, providers)
  App.tsx             the shell composition
  index.css           tailwind + SDK styles + @source lines
  lib/
    actions.ts        THE action layer (§3)
    appearance.ts     appearance state (§5)
    router.ts         the one router (§2)
    view-contract.ts  AppViewModule / ViewProps (§2)
  shell/
    apps.tsx          app identity: storyboard tiles + glyphs
    Launcher.tsx      the Launcher view
    Settings.tsx      the unified Settings view
    PresenceControl.tsx
  views/
    workbench/        index.tsx, meta.ts, routes.tsx, lib/, sections/
    scheduler/        index.tsx, meta.ts, model.ts, hooks.ts, per-route views
    attention/        index.tsx, meta.ts, model.ts, presence.ts,
                      settings-sections.tsx (§6 mounts), per-route views
    runner/           index.tsx, meta.ts, model.ts, state.ts, per-route views
```

A lane works inside its own `views/<app>/` directory and
the shared files only by the contracts above; a lane
needing a shell change names it to the coordinator
instead of editing App.tsx in parallel.

## 8. Staging rules — fonts, assets, the reference trees

- Fonts: the kit's (Inter, IBM Plex Mono, KaTeX under
  `kit/assets/`) are the only fonts. They stage by the
  bundler's inlining from the kit's home (§4) — no font
  files are copied or staged by hand. Per-app font sets
  do NOT carry (attention's Barlow/Zilla set retires
  with its local theme, §9).
- Assets: the shell stages no static assets. A view
  needing an image imports it from its own `views/<app>/`
  tree and the bundler emits it into `dist/assets/`.
- No reference trees are carried in the client: there is
  no `client/pages/` directory — the views under
  `client/src/views/<app>/` are the only client source.
- Workbench view dependencies are declared in
  `artifact/package.json`: `dompurify`, `highlight.js`,
  `katex`, `marked`, `mermaid` (plus dev `@types/katex`).

## 9. Standing exclusions

- **Scheduler:** NO Enabled switch, NO Run now / Disable
  controls (storyboard X-3 — no backing server verb
  exists; the original client is read-only by design).
  `saveJobConfig` is not wired into the views on the
  client's own initiative. The storyboard's Pings
  "Recent" group IS servable (`getPingsRecent`).
- **Per-app local themes do NOT carry:** scheduler's
  GitHub-dark palette, attention's navy/paper theme,
  runner's Okabe-Ito `theme.css` dialect all retire
  into the kit (§2b: a repo-specific look is a defect
  against the kit). Views compose on `--ui-*` tokens
  only. (The Okabe-Ito hues survive as the kit's status
  system, which is where the runner's palette already
  lived in the token base.)
- **Workbench:** build to the ORIGINAL's inventory (the
  route table in §2). The mega client's added surfaces
  with no original counterpart (Goals, Mockups as a
  surface, DatasetView, Explorer, SegmentBlocks,
  MessageThreads, Editor) are not in the table; their
  keep-or-remove disposition is the owner's, per the
  audit's C-4 — do not silently keep or silently drop.
- **Runner:** mutations stay (owner ruling) — the views call the runner actions,
  including the writes, per the restoration mapping.
- **Attention:** the shell renders no chrome inside the
  app (the old shell's pushed presence/digest values
  are gone with it); presence reaches the views only
  through §6's binding.

## 10. Build and verify

From `artifact/`:

```
bun x tsc --noEmit -p client/tsconfig.json   # typecheck
bun run build:client                          # single bundle (§1)
```

The whole chain — frozen install, typecheck, build,
parity check — is one script, and it is the only
client verification entry a gate or venue payload
runs. The frozen install is not ceremony: bun's
`file:` install copies the kit into `node_modules`,
so any build run on an existing install silently
ships the kit copy from install time — a build used
for measurement or staging always installs fresh
first (the critic re-run's N-4):

```
bun run verify:client
```

The bun version is pinned in `artifact/package.json`
(`packageManager` + `engines`: bun 1.4.4) and
`artifact/bun.lock` is generated under that exact
version; a lockfile written by a different bun is
what failed the venue gate's frozen install.

The parity check (`client/parity-check.mjs`, the last
leg of `verify:client`) asserts the staged form: one
document, one JS bundle, the kit's
`[data-palette=olive|teal]`, `[data-mode=dark]`, and
`[data-density=compact]` selectors and the AppShell
sidebar width present in the CSS, the kit fonts inlined
as data URIs, and no frame/relay markers anywhere in
the bundle.

## 11. Deviations from the kit sheet / storyboard forms

Named, per the lane brief — everything else follows the
frames as written:

1. **Tile glyphs** are drawn locally in `shell/apps.tsx`
   in the kit's icon grammar (Lucide-style SVG,
   currentColor); the storyboard tiles' exact artwork is
   not reproduced. The gradients ARE the storyboard's
   own values (`--tile-sched/wb/run/attn/set`). The kit
   imports no icon library and app glyphs arrive through
   props — this is the seam the kit sheet leaves; a
   future kit icon set replaces them in one place.
2. **Launcher Today widget:** the decision count,
   presence expiry, and next-digest label are bound
   from the glance (§6); the skeleton's unbound form —
   the decision row and the live presence line, no
   invented numbers — is retired.
3. **Settings "Night state" row** (superapp storyboard
   Settings frame) is not rendered: no frame details it
   as a control — the night ladder is the ambient
   glance's token state (attention frame 6). Revisit if
   the owner names it a setting.
4. **Presence expiry:** the Expires group represents
   the served expiry (§6 — a checked Current choice
   when it matches no preset); the frame's instance
   labels are the presets' render-time computations,
   not stored values.
5. **Search slot** is per-surface, not per-app: it
   renders where the surface's search behaviour exists.
   A view module's declared `searchPlaceholder(subroute)`
   governs when present — the scheduler declares it for
   `/jobs` only, and a declared `undefined` is honest
   absence, never a fall back to the per-app map;
   modules without the member (workbench) keep the
   per-app default from the storyboards. At non-phone
   widths ≤1024px the slot renders as a row at the head
   of the content region instead of in the TopBar (the
   kit PhoneShell's own form), so the breadcrumb and
   the presence control keep the bar (critic B-3).
6. **Launcher and Settings** render as standalone shell
   views (the storyboard's own presentation of them),
   outside AppShell — on phone they are single-column
   full-width, without the PhoneShell wrapper.
7. **The entry preview is a full page, and the one
   iframe survives inside it (FU-1, owner ruling).** The original viewer's
   embedded stage — the entry's page rendered in a box
   inside the drill-in — is replaced by a full-page
   route (`#/workbench/p/<slug>/preview/<entryId>`,
   §2): the drill-in's frame is the door, the page's
   top bar carries a back control (to the drill-in),
   the entry's title, and an info action whose surface
   is the kit's one Sheet (the popup drawer at phone
   width, the docked panel on desktop) over the entry
   record's own fields. The page's content area is the
   stage's own rendering, unchanged: the `getEntryPage`
   bytes in a sandboxed `srcDoc` iframe
   (`allow-scripts`, opaque origin) — the parity
   check's one sanctioned iframe, asserted in its
   full-page form (the page component exists, the
   embedded stage is gone by name, the route parses
   and builds, the drill-in navigates). The
   server-composed alternative — the backend serving
   the entry as a full document with the chrome
   composed around it — was evaluated first and
   refused on evidence: the companion server binds
   loopback only, and its address resolves on the
   reader's own device (the stage's founding
   constraint), so no reader's browser can navigate to
   it; the platform serves this client's one document
   from the client's own origin, where a served entry
   document would run its scripts with the client's
   origin privileges — the surface the sandbox exists
   to close; and chrome composed by the backend would
   be a second implementation of the kit's chrome,
   against §1/§4. Behaviour of record is preserved
   exactly, measured against the stage before the
   change: the same bytes, the same sandbox, picks
   registering in the page (the answered counter
   advancing) for the life of the page's document —
   the runtime's storage is best-effort and inoperative
   inside the opaque origin, as it was in the stage.
   The preview page fills the content region's full
   height under the top bar: the view module declares
   the fill per subroute (view contract `fillsContent`),
   the shell's main becomes a full-height flex column
   for that route alone, the mount flexes as its
   flexible child, and the exhibit iframe fills the
   remainder and scrolls its own document internally.
