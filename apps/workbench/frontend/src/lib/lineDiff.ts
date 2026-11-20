// Simple line diff (context / add / del) between two text
// snapshots — shared by the peek's Diff tab (components/ui
// re-exports it) and the adapters' diff model. It lives in
// lib/ so the seam code the validate harness bundles
// headlessly never pulls a component module (and its kit /
// react imports) into the bundle graph.

export function lineDiff(
  head: string,
  current: string,
): { kind: "ctx" | "add" | "del"; text: string }[] {
  const a = head.split("\n");
  const b = current.split("\n");
  const out: { kind: "ctx" | "add" | "del"; text: string }[] = [];
  // LCS over lines (files here are small).
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      out.push({ kind: "ctx", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ kind: "del", text: a[i] });
      i++;
    } else {
      out.push({ kind: "add", text: b[j] });
      j++;
    }
  }
  while (i < m) out.push({ kind: "del", text: a[i++] });
  while (j < n) out.push({ kind: "add", text: b[j++] });
  return out;
}
