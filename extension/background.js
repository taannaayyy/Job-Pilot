// Receives captures from the LinkedIn page, keeps them in a queue while Job Pilot is closed
// (the app only runs while its window is open), and delivers them when it is running.

import { apiUrl, checkConnection, getSettings } from "./lib.js";

const MAX_LOGO_BYTES = 512 * 1024;

async function getQueue() {
  const { queue = [] } = await chrome.storage.local.get("queue");
  return queue;
}

async function setQueue(queue) {
  await chrome.storage.local.set({ queue });
  await updateBadge(queue.length);
}

async function updateBadge(count) {
  await chrome.action.setBadgeBackgroundColor({ color: "#d97706" });
  await chrome.action.setBadgeText({ text: count ? String(count) : "" });
  await chrome.action.setTitle({
    title: count ? `Job Pilot: ${count} saved job${count > 1 ? "s" : ""} waiting for the app` : "Job Pilot",
  });
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** LinkedIn's logo links expire, so the logo is downloaded now, in the user's own browser. */
async function fetchLogo(url) {
  try {
    if (!url || new URL(url).hostname !== "media.licdn.com") return null;
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    const buffer = await res.arrayBuffer();
    return buffer.byteLength <= MAX_LOGO_BYTES ? toBase64(buffer) : null;
  } catch {
    return null;
  }
}

/** One delivery attempt. Returns {state: "saved" | "duplicate" | "rejected", ...} or throws when the app can't be reached. */
async function deliver(payload, { token, port }) {
  const res = await fetch(apiUrl(port, "/capture"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-JobPilot-Token": token },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10000),
  });
  if (res.status === 401) throw new Error("bad_token");
  const body = await res.json().catch(() => ({}));
  if (!res.ok) return { state: "rejected", message: typeof body.detail === "string" ? body.detail : `Error ${res.status}` };
  return { state: body.created ? "saved" : "duplicate", job: body.job };
}

let flushing = null;

/** Sends every queued capture; stops at the first one that can't reach the app. */
function flush() {
  flushing ??= (async () => {
    try {
      const settings = await getSettings();
      if ((await getQueue()).length === 0 || (await checkConnection(settings)) !== "ok") return;
      for (;;) {
        const [next] = await getQueue();
        if (!next) return;
        try {
          await deliver(next.payload, settings);
        } catch {
          return; // closed again, or the key changed; try later
        }
        // Delivered, already saved, or refused by the app: none of these get better by retrying.
        await setQueue((await getQueue()).filter((item) => item.payload.linkedin_job_id !== next.payload.linkedin_job_id));
      }
    } finally {
      flushing = null;
    }
  })();
  return flushing;
}

async function capture(payload, logoUrl) {
  payload = { ...payload, logo_base64: await fetchLogo(logoUrl) };
  const settings = await getSettings();
  if (settings.token) {
    try {
      const result = await deliver(payload, settings);
      flush(); // the app is up: send anything still waiting
      return result;
    } catch {
      // fall through to the queue
    }
  }
  const queue = await getQueue();
  if (!queue.some((item) => item.payload.linkedin_job_id === payload.linkedin_job_id)) {
    queue.push({ payload, queuedAt: Date.now() });
    await setQueue(queue);
  }
  return { state: "queued", reason: await checkConnection(settings), queued: queue.length };
}

async function status() {
  return { connection: await checkConnection(), queued: (await getQueue()).length };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handlers = {
    capture: () => capture(message.payload, message.logoUrl),
    status,
    sync: async () => {
      await flush();
      return status();
    },
  };
  const handler = handlers[message?.type];
  if (!handler) return false;
  handler().then(sendResponse, (e) => sendResponse({ state: "error", message: String(e?.message ?? e) }));
  return true; // answers asynchronously
});

chrome.runtime.onInstalled.addListener(async () => {
  chrome.alarms.create("sync", { periodInMinutes: 1 });
  if (!(await getSettings()).token) chrome.runtime.openOptionsPage();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("sync", { periodInMinutes: 1 });
  flush();
});

chrome.alarms.onAlarm.addListener((alarm) => alarm.name === "sync" && flush());

chrome.storage.onChanged.addListener((changes) => {
  if (changes.token || changes.port) flush();
});

getQueue().then((queue) => updateBadge(queue.length));
