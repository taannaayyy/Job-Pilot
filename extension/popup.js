import { STATE_TEXT } from "./lib.js";

const DOT = { ok: "ok", closed: "warn", no_token: "err", bad_token: "err", other_app: "err" };

function show({ connection, queued }) {
  document.getElementById("dot").className = `dot ${DOT[connection] ?? ""}`;
  document.getElementById("state").textContent = STATE_TEXT[connection] ?? "Unknown state";
  const queue = document.getElementById("queue");
  queue.hidden = !queued;
  queue.textContent = `${queued} saved job${queued === 1 ? "" : "s"} waiting to be added to the app.`;
  document.getElementById("sync").hidden = !queued || connection !== "ok";
}

document.getElementById("settings").onclick = () => chrome.runtime.openOptionsPage();
document.getElementById("sync").onclick = async (e) => {
  e.target.disabled = true;
  show(await chrome.runtime.sendMessage({ type: "sync" }));
  e.target.disabled = false;
};

// Opening the popup also delivers anything waiting, when the app is up.
chrome.runtime.sendMessage({ type: "sync" }).then(show);
