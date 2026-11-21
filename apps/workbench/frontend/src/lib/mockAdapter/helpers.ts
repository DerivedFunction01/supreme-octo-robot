// Mock adapter helpers: the content hash the demo
// store stamps its saves with, HTML escaping, the
// stand-in page a specimen entry serves as its own
// page, and the repo file-tree walk.

import type { Entry, RepoFile } from "../types";


export function shaOf(content: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < content.length; i++) {
    h ^= content.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0").slice(0, 6);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** The mock's stand-in for an entry's own page: a complete
 *  document authored in the entry's recorded mode, served
 *  through entryPage in the byte route's shape. The demo's
 *  specimens have no files on disk; in the live store this
 *  is the entry's own file, served byte-for-byte. The
 *  page's script runs in the stage's sandboxed frame, as
 *  a served page's would. */
export function standinEntryPage(e: Entry): string {
  const dark = e.mode === "Dark";
  const bg = dark ? "#22251a" : "#f7f6ef";
  const ink = dark ? "#e8e6da" : "#2c2f22";
  const sub = dark ? "#a9ad97" : "#6a6e58";
  const bar = dark ? "#3a3f2c" : "#59652c";
  const line = dark ? "#565b45" : "#d8d5c2";
  const title = escapeHtml(e.title);
  return [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8">',
    `<title>${title}</title>`,
    `<style>body{font-family:system-ui,sans-serif;background:${bg};color:${ink};margin:0;padding:30px}` +
      `h1{font-size:22px;margin:0 0 6px}.sub{color:${sub};font-size:13px;margin:0 0 22px}` +
      `.bar{height:14px;border-radius:4px;background:${bar};width:38%;margin-bottom:12px}` +
      `.ln{height:10px;border-radius:4px;background:${line};margin-bottom:9px}` +
      `.row{display:flex;gap:8px;margin:16px 0}.blk{height:38px;width:58px;border-radius:5px}</style>`,
    "</head><body>",
    `<div class="bar"></div><h1>${title}</h1>`,
    `<p class="sub">${escapeHtml(e.project)} · ${escapeHtml(e.viewport ?? "Desktop")} · ${escapeHtml(e.mode ?? "Light")} — the specimen's own page, as authored.</p>`,
    '<div class="ln" style="width:86%"></div><div class="ln" style="width:68%"></div>',
    '<div class="row"><div class="blk" style="background:#67742f"></div><div class="blk" style="background:#0f766e"></div><div class="blk" style="background:#0072B2"></div><div class="blk" style="background:#D55E00"></div></div>',
    '<div class="ln" style="width:56%"></div>',
    '<p class="sub" id="stamp"></p>',
    '<script>document.getElementById("stamp").textContent = "Page script running · rendered " + new Date().toLocaleTimeString();</script>',
    "</body></html>",
  ].join("\n");
}

export function findFile(files: RepoFile[], path: string): RepoFile | undefined {
  const parts = path.split("/");
  let level: RepoFile[] | undefined = files;
  let found: RepoFile | undefined;
  for (const part of parts) {
    found = level?.find((f) => f.name === part);
    if (!found) return undefined;
    level = found.children;
  }
  return found;
}
