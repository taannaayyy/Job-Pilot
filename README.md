# Job Pilot

A local, single-user macOS app for tracking job applications. Everything stays on your Mac in one SQLite file. There are no accounts and no cloud, and nothing runs in the background.

## Features

- **Save jobs from LinkedIn.** A Chrome extension adds a **Save to Job Pilot** button to LinkedIn job pages. One click saves the title, company, company logo, location, work mode, job type and description. The same posting is never saved twice, even if you also pasted its link by hand. Jobs you save while Job Pilot is closed wait in the extension and are added the next time you open the app.
- **Board and table views.** Use the kanban board with drag and drop, or a sortable table.
- **Statuses.** A job moves through Saved, Applied, Screening, Interview, Awaiting decision (all interviews done, waiting for their answer), Offer, Rejected and Ghosted.
- **Automatic applied date.** It is stamped the first time a job moves to Applied or a later stage.
- **Status history** for every job, plus notes, a next action, the job URL, job type (full-time, part-time, internship, contract), work mode and source.
- **Company logos.** Add a company's website and its logo appears next to the name. Companies without a website get a colored badge with their initials. Each logo is downloaded once and saved on your Mac.
- **Istanbul locations.** City defaults to Istanbul. Pick a district, or just a side ("All of Anadolu Yakası"), from a searchable list grouped by Anadolu Yakası and Avrupa Yakası. Or choose "Other city" and type it.
- **Search and filters.** Search by company, title or district, and filter by status, job type, work mode and location (Anadolu, Avrupa or other cities).
- **Watchlist.** Save the companies, startups, research centers and universities you would like to work at, even before they have a job you want. Each card links to its careers page and its LinkedIn jobs, and records whether it was hiring when you last checked. Cards that haven't been checked for two weeks are marked as due. Add a job there in one click, or star a company from any job.
- **Company deduplication.** "Acme AI" and "acme ai" count as the same company.
- **Light, night and system themes.** The native title bar follows the theme.
- **Native macOS window** with the usual shortcuts.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Node 20+.

```sh
cd frontend && npm install && cd ..
./packaging/build_app.sh
cp -R "dist/Job Pilot.app" /Applications/
```

Open **Job Pilot** from Spotlight or Launchpad.

### Chrome extension

1. In Job Pilot, click **Extension** at the top, then **Open Chrome**. Chrome opens its extensions page, and the extension's folder location is copied for you.
2. In Chrome, turn on **Developer mode**, click **Load unpacked**, press Shift+Cmd+G, paste with Cmd+V, press Return and click **Select**.
3. The extension's settings open. Paste the key shown in Job Pilot's Extension dialog and click Save.

Chrome doesn't let apps install extensions themselves, so this is done once by hand. Publishing to the Chrome Web Store, which would make it a one-click install, is planned.

The extension only reads the job page you have open when you click its button. It never browses LinkedIn on its own. After updating the app, click **Open Chrome** again and press the reload button on the extension.

The app runs only while its window is open. Closing the window stops it completely, and nothing starts at login.

The app listens on port 8765, where the extension looks for it. If another program already uses that port, Job Pilot says which one and lets you quit or open anyway. If you open anyway, everything works except saving from LinkedIn, which waits until the port is free.

To update after code changes, rebuild and replace the installed copy:

```sh
./packaging/build_app.sh
rm -rf "/Applications/Job Pilot.app" && cp -R "dist/Job Pilot.app" /Applications/
```

### Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Cmd+M | Minimize |
| Cmd+W | Close window (quits the app) |
| Cmd+Q | Quit |
| Cmd+Z / Shift+Cmd+Z | Undo / Redo in text fields |
| Ctrl+Cmd+F | Full screen |
| Esc | Close the add form or the job panel |

## Your data

Jobs are stored in:

```
~/Library/Application Support/JobPilot/jobpilot.db
```

Downloaded company logos are kept in the `logos` folder next to it and are downloaded again if deleted.

The extension key is in `extension-key` in the same folder.

To back up, copy `jobpilot.db`. The app and the development server both use this same file. To use a different one, set `JOBPILOT_DB=/path/to/other.db`.

## Development

Run the backend and the UI with live reload:

```sh
./dev.sh
```

Then open http://127.0.0.1:5173.

### Ports

| | Default | Change with |
| --- | --- | --- |
| UI (Vite) | 5173 | `JOBPILOT_UI_PORT` |
| Backend (FastAPI) | 8766 | `JOBPILOT_PORT` |
| Installed app | 8765 | |

If another app is already using one of these ports, `dev.sh` says which process holds it and stops. To run on other ports:

```sh
JOBPILOT_UI_PORT=5180 JOBPILOT_PORT=8770 ./dev.sh
```

To see what is using a port: `lsof -nP -iTCP:5173 -sTCP:LISTEN`.

The installed app uses 8765 and `dev.sh` uses 8766, so both can run at the same time. To point the extension at the development server, set its port to 8766 under **Advanced** in the extension's settings. Both use the same database and extension key.

### Tests

```sh
cd backend && uv run pytest
```

### Schema changes

Edit `backend/src/jobpilot/models.py`, then generate a migration:

```sh
cd backend && uv run alembic revision --autogenerate -m "describe change"
```

Migrations run automatically when the backend starts, in both the app and `dev.sh`.

### App icon

The icon is drawn in `packaging/icon.svg`. After editing it, run `./packaging/make_icon.sh` to regenerate `icon.icns`. This needs Google Chrome.

## Project structure

```
backend/                 Python: FastAPI, SQLAlchemy, Alembic (managed with uv)
  src/jobpilot/
    api.py               REST endpoints under /api
    capture.py           Endpoints for the Chrome extension
    linkedin.py          Reads LinkedIn job IDs, locations and job types
    logos.py             Fetches and caches company logos
    models.py            Database tables
    desktop.py           Native window, menus, title bar theme
    migrations/          Alembic migrations
  tests/
frontend/                React + TypeScript + Vite
  src/
    App.tsx              Main screen, filters, theme switch
    locations.ts         Istanbul districts by side
    components/          Board, table, form, detail panel
    styles.css           Themes and animations
extension/               Chrome extension (Manifest V3)
  content.js             Button on LinkedIn job pages, reads the open job
  background.js          Queue while the app is closed, delivery to the app
packaging/               PyInstaller spec, build script, icon
dev.sh                   Runs backend + UI for development
```

## Stack

FastAPI, SQLAlchemy 2, Alembic, SQLite · React 18, TypeScript, Vite · pywebview, PyInstaller · Chrome extension (Manifest V3)
