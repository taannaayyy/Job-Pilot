import { DEFAULT_PORT, STATE_TEXT, checkConnection, getSettings } from "./lib.js";

const DOT = { ok: "ok", closed: "warn", no_token: "err", bad_token: "err", other_app: "err" };
const token = document.getElementById("token");
const port = document.getElementById("port");

async function refresh() {
  const state = await checkConnection();
  document.getElementById("dot").className = `dot ${DOT[state] ?? ""}`;
  document.getElementById("state").textContent = STATE_TEXT[state];
}

document.getElementById("form").onsubmit = async (e) => {
  e.preventDefault();
  await chrome.storage.local.set({ token: token.value.trim(), port: Number(port.value) || DEFAULT_PORT });
  const saved = document.getElementById("saved");
  saved.classList.add("show");
  setTimeout(() => saved.classList.remove("show"), 1500);
  refresh();
};

const settings = await getSettings();
token.value = settings.token;
port.value = settings.port;
refresh();
setInterval(refresh, 4000);
