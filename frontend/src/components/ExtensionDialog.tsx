import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ExtensionInfo } from "../types";
import { useClosing } from "../useClosing";
import { CheckIcon, CopyIcon, ExternalIcon, FolderIcon } from "./Icons";

interface Props {
  onClose: () => void;
}

function lastSeen(iso: string) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  return minutes < 1
    ? "just now"
    : minutes === 1
      ? "a minute ago"
      : `${minutes} minutes ago`;
}

export default function ExtensionDialog({ onClose }: Props) {
  const [info, setInfo] = useState<ExtensionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pathCopied, setPathCopied] = useState(false);
  const [closing, close] = useClosing(onClose);
  const keyRef = useRef<HTMLInputElement>(null);

  // Polls so the status turns green as soon as the key is pasted into the extension.
  useEffect(() => {
    const load = () =>
      api.getExtension().then(setInfo, (e) => setError(e.message));
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const copy = async () => {
    if (!info) return;
    try {
      await navigator.clipboard.writeText(info.token);
    } catch {
      keyRef.current?.select();
      document.execCommand("copy");
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const run = (action: () => Promise<unknown>) => async () => {
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className={`overlay ${closing ? "closing" : ""}`} onMouseDown={close}>
      <div
        className="modal"
        role="dialog"
        aria-labelledby="ext-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="ext-title">Chrome extension</h2>
        <p className="modal-hint">
          Save the LinkedIn job or company you are looking at with one click. What you
          save while Job Pilot is closed is added the next time you open it.
        </p>

        {info && (
          <div className="ext-status">
            {info.port_blocked_by ? (
              <>
                <span className="dot warn" />
                {info.port_blocked_by} is using port {info.capture_port}, so the
                extension can't reach Job Pilot. Quit it and reopen Job Pilot.
              </>
            ) : info.last_seen ? (
              <>
                <span className="dot ok" />
                Extension connected, last seen {lastSeen(info.last_seen)}
              </>
            ) : (
              <>
                <span className="dot" />
                The extension hasn't connected since Job Pilot opened.
              </>
            )}
          </div>
        )}

        <ol className="ext-steps">
          <li>
            <strong>Install it in Chrome</strong>
            <p>
              Job Pilot opens Chrome's extensions page and copies the
              extension's location for you. Then in Chrome:
            </p>
            <ol className="ext-substeps">
              <li>
                Turn on <b>Developer mode</b> (top right)
              </li>
              <li>
                Click <b>Load unpacked</b> (top left)
              </li>
              <li>
                Press <kbd>⇧⌘G</kbd>, then <kbd>⌘V</kbd> and <kbd>Return</kbd>,
                and click <b>Select</b>
              </li>
            </ol>
            {info?.folder_available && (
              <div className="row">
                <button
                  type="button"
                  className="primary"
                  onClick={run(async () => {
                    await api.installExtension();
                    setPathCopied(true);
                  })}
                >
                  <ExternalIcon />
                  Open Chrome
                </button>
                {pathCopied && (
                  <span className="ext-note">
                    <CheckIcon /> Location copied
                  </span>
                )}
                <span className="spacer" />
                <button
                  type="button"
                  className="link quiet"
                  onClick={run(api.revealExtension)}
                >
                  <FolderIcon />
                  Show in Finder
                </button>
              </div>
            )}
          </li>
          <li>
            <strong>Connect it to this app</strong>
            <p>
              Copy this key and paste it into the extension's settings, which
              open after installing.
            </p>
            <div className="row">
              <input
                ref={keyRef}
                className="ext-key"
                readOnly
                value={info?.token ?? ""}
                onFocus={(e) => e.target.select()}
              />
              <button
                type="button"
                className={copied ? "success" : ""}
                onClick={copy}
                disabled={!info}
              >
                {copied ? <CheckIcon /> : <CopyIcon />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </li>
        </ol>

        {error && <div className="error">{error}</div>}

        <div className="actions">
          <button
            type="button"
            className="danger"
            onClick={run(async () => {
              if (
                !confirm(
                  "Make a new key? The extension stops working until you paste the new one.",
                )
              )
                return;
              setInfo(await api.newExtensionKey());
            })}
          >
            Make a new key
          </button>
          <span className="spacer" />
          <button type="button" onClick={close}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
