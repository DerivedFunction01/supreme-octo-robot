// The mounted tree for the integration entry. Live mode
// awaits the adapter's first load before mounting so the
// published app never flashes the empty snapshot (the
// scheduler embedded entry's rule).

import { createRoot } from "react-dom/client";
import App from "./App";
import { adapter } from "./venue";
import { LiveVenueAdapter } from "./venue/live-adapter";
import "./index.css";

async function boot(): Promise<void> {
  if (adapter instanceof LiveVenueAdapter) {
    await adapter.ready();
  }
  const el = document.getElementById("root");
  if (!el) {
    throw new Error("integration mount: #root element missing");
  }
  createRoot(el).render(<App />);
}

void boot();
