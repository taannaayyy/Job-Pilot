// Runs on LinkedIn job pages. Adds a "Save to Job Pilot" button and, when clicked, reads the
// job the user has open. It never opens pages, scrolls or clicks anything on LinkedIn itself.

(() => {
  const MAX_DESCRIPTION = 100_000;

  function jobIdFromUrl(href) {
    const url = new URL(href);
    const view = url.pathname.match(/\/jobs\/view\/(?:[^/]*-)?(\d{6,})/);
    if (view) return view[1];
    const current = url.searchParams.get("currentJobId");
    return current && /^\d+$/.test(current) ? current : null;
  }

  const clean = (s) => (s ?? "").replace(/[ \t ]+/g, " ").replace(/\n\s*\n+/g, "\n\n").trim();
  const textOf = (el) => clean(el?.innerText ?? el?.textContent);

  function first(root, selectors) {
    for (const selector of selectors) {
      for (const el of root.querySelectorAll(selector)) if (textOf(el)) return el;
    }
    return null;
  }

  /** Public job pages (and some signed-in ones) describe the job in JSON-LD. */
  function jsonLdPosting() {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const data = JSON.parse(script.textContent);
        const items = [data, ...(data["@graph"] ?? [])].flat();
        const posting = items.find((d) => d?.["@type"] === "JobPosting");
        if (posting) return posting;
      } catch {
        // not JSON we understand
      }
    }
    return null;
  }

  function htmlToText(html) {
    // JSON-LD descriptions are escaped HTML ("&lt;p&gt;"), so decoding once can still leave tags.
    let text = html ?? "";
    for (let i = 0; i < 2 && /<[a-z][^>]*>|&[a-z]+;/i.test(text); i++) {
      text = new DOMParser().parseFromString(text, "text/html").body.innerText ?? "";
    }
    return clean(text);
  }

  function extract() {
    const ld = jsonLdPosting();
    // The pane with the open job; on search pages the list of results sits next to it.
    const pane =
      document.querySelector(".jobs-search__job-details--container, .jobs-details, .job-view-layout, .scaffold-layout__detail") ??
      document.querySelector("main") ??
      document.body;

    const titleEl = first(pane, [
      ".job-details-jobs-unified-top-card__job-title h1",
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".top-card-layout__title",
      "h1",
    ]);
    const companyEl = first(pane, [
      ".job-details-jobs-unified-top-card__company-name a",
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name",
      ".topcard__org-name-link",
      'a[href*="/company/"]',
    ]);

    // The job's header: the closest box around the title that also holds the company.
    let header = titleEl;
    while (header && header !== pane && !(companyEl && header.contains(companyEl))) header = header.parentElement;
    header = header ?? pane;

    const companyLink = companyEl?.closest('a[href*="/company/"]') ?? header.querySelector('a[href*="/company/"]');
    const logo = [...header.querySelectorAll("img"), ...pane.querySelectorAll('a[href*="/company/"] img')].find((img) =>
      (img.currentSrc || img.src).startsWith("https://media.licdn.com/"),
    );

    const locationEl = first(header, [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".job-details-jobs-unified-top-card__tertiary-description-container",
      ".jobs-unified-top-card__bullet",
      ".topcard__flavor--bullet",
    ]);
    const descriptionEl = first(pane, [
      "#job-details",
      ".jobs-description__content",
      ".jobs-description-content__text",
      ".jobs-box__html-content",
      ".show-more-less-html__markup",
      ".description__text",
    ]);
    // Browser tab: "Machine Learning Engineer | Acme AI | LinkedIn".
    const [tabTitle, tabCompany] = document.title.replace(/^\(\d+\)\s*/, "").split(" | ");
    const ldPlace = ld?.jobLocation?.address ?? [ld?.jobLocation].flat()[0]?.address;

    return {
      linkedin_job_id: jobIdFromUrl(location.href),
      url: location.href,
      title: textOf(titleEl) || ld?.title || (tabCompany ? tabTitle : "") || "",
      company: textOf(companyEl) || ld?.hiringOrganization?.name || (tabCompany ?? ""),
      company_linkedin_url: companyLink?.href ?? ld?.hiringOrganization?.sameAs ?? null,
      location:
        textOf(locationEl).split("·")[0].trim() ||
        [ldPlace?.addressLocality, ldPlace?.addressRegion, ldPlace?.addressCountry].filter(Boolean).join(", ") ||
        null,
      workplace: ld?.jobLocationType === "TELECOMMUTE" ? "Remote" : null,
      employment_type: [ld?.employmentType].flat().filter(Boolean).join(" ") || null,
      details: textOf(header).slice(0, 4000) || null,
      description: (textOf(descriptionEl) || htmlToText(ld?.description)).slice(0, MAX_DESCRIPTION) || null,
      logoUrl: logo ? logo.currentSrc || logo.src : ld?.hiringOrganization?.logo ?? null,
    };
  }

  // ---- The button, in a shadow root so LinkedIn's styles don't reach it.

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:24px;bottom:24px;z-index:2147483646;display:none";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      .card { display: flex; flex-direction: column; gap: 8px; align-items: stretch; max-width: 320px;
        background: #171a20; color: #e6e8ec; border: 1px solid #2a2f39; border-radius: 14px; padding: 6px;
        box-shadow: 0 10px 30px rgba(0,0,0,.35); animation: in .22s cubic-bezier(.2,.8,.2,1); }
      @keyframes in { from { opacity: 0; transform: translateY(8px) scale(.98); } }
      button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 0; cursor: pointer;
        font-size: 14px; font-weight: 600; border-radius: 10px; padding: 10px 14px; color: #fff; background: #2f6fde;
        transition: background .15s, transform .1s; }
      button:hover { background: #4a86f0; } button:active { transform: scale(.97); }
      button:disabled { cursor: default; } button:disabled:not(.done, .wait) { opacity: .7; }
      .done:disabled:hover { background: #15803d; } .wait:disabled:hover { background: #b45309; }
      button.quiet { background: transparent; color: #8b93a3; font-weight: 500; padding: 6px 10px; }
      button.quiet:hover { color: #e6e8ec; background: #1e222a; }
      .done { background: #15803d; } .done:hover { background: #16a34a; }
      .wait { background: #b45309; } .wait:hover { background: #d97706; }
      .msg { font-size: 12.5px; line-height: 1.4; color: #8b93a3; padding: 0 6px 4px; }
      .msg.err { color: #f87171; }
      form { display: flex; flex-direction: column; gap: 6px; padding: 4px; }
      label { font-size: 12px; color: #8b93a3; display: flex; flex-direction: column; gap: 3px; }
      input { font-size: 13px; padding: 7px 9px; border-radius: 8px; border: 1px solid #2a2f39; background: #0f1115; color: #e6e8ec; }
      input:focus { outline: 2px solid #5b8cf5; outline-offset: -1px; }
      .row { display: flex; gap: 6px; justify-content: flex-end; }
      svg { width: 16px; height: 16px; flex: none; }
      .spin { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.35); border-top-color: #fff; border-radius: 50%;
        animation: spin .7s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
    </style>
    <div class="card"></div>`;
  const card = root.querySelector(".card");
  document.documentElement.append(host);

  const ICON = {
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  };
  const REASON = {
    no_token: "Open the extension's settings and paste the key from Job Pilot.",
    bad_token: "The extension key is wrong. Copy it again from Job Pilot.",
    closed: "Job Pilot is closed. It will be added when you open the app.",
    other_app: "Another program is using Job Pilot's port. It will be added once the app can be reached.",
  };

  // Result per LinkedIn job, so switching jobs on a search page shows the right state.
  const results = new Map();
  let currentId = null;

  function escape(s) {
    return String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  }

  function render() {
    const result = results.get(currentId);
    if (!result) {
      card.innerHTML = `<button class="save">${ICON.plus} Save to Job Pilot</button>`;
      card.querySelector(".save").onclick = () => save();
      return;
    }
    if (result.state === "busy") {
      card.innerHTML = `<button disabled><span class="spin"></span> Saving…</button>`;
    } else if (result.state === "saved" || result.state === "duplicate") {
      card.innerHTML = `<button class="done" disabled>${ICON.check} ${result.state === "saved" ? "Saved to Job Pilot" : "Already in Job Pilot"}</button>`;
    } else if (result.state === "queued") {
      card.innerHTML = `<button class="wait" disabled>${ICON.clock} Saved, will sync</button>
        <div class="msg">${escape(REASON[result.reason] ?? REASON.closed)}</div>`;
    } else if (result.state === "form") {
      renderForm(result.data);
    } else {
      card.innerHTML = `<button class="save">${ICON.plus} Try again</button><div class="msg err">${escape(result.message ?? "Something went wrong.")}</div>`;
      card.querySelector(".save").onclick = () => save();
    }
  }

  /** Shown when the page didn't give a title or company (LinkedIn changes its layout now and then). */
  function renderForm(data) {
    card.innerHTML = `
      <form>
        <div class="msg">Couldn't read everything on this page. Check these:</div>
        <label>Job title <input name="title" required maxlength="300"></label>
        <label>Company <input name="company" required maxlength="200"></label>
        <div class="row"><button type="button" class="quiet cancel">Cancel</button><button type="submit">${ICON.plus} Save</button></div>
      </form>`;
    const form = card.querySelector("form");
    // Not form.title: that is the form's own title attribute.
    const title = form.querySelector('[name="title"]');
    const company = form.querySelector('[name="company"]');
    title.value = data.title;
    company.value = data.company;
    (data.title ? company : title).focus();
    form.querySelector(".cancel").onclick = () => {
      results.delete(currentId);
      render();
    };
    form.onsubmit = (e) => {
      e.preventDefault();
      send({ ...data, title: title.value.trim(), company: company.value.trim() });
    };
  }

  function save() {
    const data = extract();
    if (!data.linkedin_job_id) return;
    if (!data.title || !data.company) {
      results.set(data.linkedin_job_id, { state: "form", data });
      render();
      return;
    }
    send(data);
  }

  async function send(data) {
    const id = data.linkedin_job_id;
    const { logoUrl, ...payload } = data;
    results.set(id, { state: "busy" });
    render();
    let result;
    try {
      result = await chrome.runtime.sendMessage({ type: "capture", payload, logoUrl });
    } catch {
      result = { state: "error", message: "The extension was updated. Reload this page and try again." };
    }
    results.set(id, result?.state ? result : { state: "error" });
    if (id === currentId) render();
  }

  // LinkedIn is a single-page app: watch for the open job changing without a page load.
  function sync() {
    const id = jobIdFromUrl(location.href);
    host.style.display = id ? "block" : "none";
    if (id !== currentId) {
      currentId = id;
      if (results.get(id)?.state === "form") results.delete(id);
      render();
    }
  }
  sync();
  setInterval(sync, 700);
})();
