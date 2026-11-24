"use strict";
/* Venue identity for the panel: the display labels for the
 * served venue set and the budget section's other-venue rows.
 * The core serves one budget entry per (venue, account); the
 * home snapshot in app.js covers the home venue's primary
 * account, and every other entry renders here as a named row —
 * a budget-less venue with no figures at all, a foreign
 * account with its caps only (its balance is dialed on its own
 * venue, not from here). Loads after app.js and uses its
 * helpers (esc, capText) and the merged state S. */

const VENUE_LABELS = { colab: "Colab", local: "Local" };

function venueLabel(v) {
  return VENUE_LABELS[v] || v || "—";
}

function otherVenueRows() {
  return ((S && S.budgets) || [])
    .filter((e) => !(e.venue === "colab" && (e.account == null || e.account === "primary")))
    .map((e) => {
      const name = `${venueLabel(e.venue)}${e.label ? ` · ${esc(e.label)}` : ""}`;
      if (!e.budget) return `<div class="row"><span class="lab">${esc(name)}</span><span class="num">No budget</span></div>`;
      const c = e.budget.caps || {};
      return `<div class="row"><span class="lab">${esc(name)}</span><span class="num">Caps ${capText(c.daily)} / ${capText(c.monthly)}</span></div>`;
    })
    .join("");
}
