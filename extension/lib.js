// Shared by the background worker, the popup and the settings page.

// The installed Job Pilot app listens here; the development backend (dev.sh) uses 8766.
export const DEFAULT_PORT = 8765;

export async function getSettings() {
  const { token = "", port = DEFAULT_PORT } = await chrome.storage.local.get(["token", "port"]);
  return { token: token.trim(), port: Number(port) || DEFAULT_PORT };
}

export function apiUrl(port, path) {
  return `http://127.0.0.1:${port}/api${path}`;
}

/**
 * What is on the other end of the port:
 * "ok", "no_token", "bad_token", "closed" (nothing answers) or "other_app" (something that isn't Job Pilot).
 */
export async function checkConnection({ token, port } = {}) {
  if (port === undefined) ({ token, port } = await getSettings());
  let body;
  try {
    const res = await fetch(apiUrl(port, "/ping"), {
      headers: token ? { "X-JobPilot-Token": token } : {},
      signal: AbortSignal.timeout(2500),
    });
    body = await res.json();
  } catch (e) {
    // A timeout or refused connection means the app is closed; a non-JSON answer is another program.
    return e instanceof SyntaxError ? "other_app" : "closed";
  }
  if (body?.app !== "jobpilot") return "other_app";
  if (!token) return "no_token";
  return body.token_ok ? "ok" : "bad_token";
}

export const STATE_TEXT = {
  ok: "Connected to Job Pilot",
  no_token: "Paste the extension key from Job Pilot in the settings",
  bad_token: "The extension key is wrong. Copy it again from Job Pilot",
  closed: "Job Pilot is closed. What you save syncs when you open it",
  other_app: "Another program is using the port. Quit it, then reopen Job Pilot",
};
