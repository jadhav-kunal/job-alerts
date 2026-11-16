// Job Alerts Autofill: fills an application form from config/profile.yaml, attaches the job's resume and cover
// letter, and marks the Discord alert as applied once the site confirms the submission. It never clicks Submit.
(() => {
  if (window.__jobAlertsLoaded) return;
  window.__jobAlertsLoaded = true;

  // Tests inject a fake transport into the page; the extension uses the background worker.
  const send = (msg) =>
    window.__jobAlertsTestSend ? window.__jobAlertsTestSend(msg) : chrome.runtime.sendMessage(msg);
  const api = (path, method = "GET", body) => send({ type: "api", path, method, body });
  // Live status for the panel, which may be on the outer page while this frame does the work. Every step also
  // goes to the browser console ("[JobAlerts]") and to data/extension.log through the helper.
  const progress = (text) => {
    log(text);
    if (root) setStatus(text);
    else if (window.top !== window && !window.__jobAlertsTestSend) send({ type: "progress", text }).catch(() => {});
  };
  let logBuf = [], logTimer = null;
  function log(text) {
    console.log("[JobAlerts]", text);
    if (window.__jobAlertsTestSend) return;
    logBuf.push(`${new Date().toISOString().slice(11, 23)} ${location.host} ${text}`);
    logTimer ||= setTimeout(() => {
      const lines = logBuf; logBuf = []; logTimer = null;
      api("/api/log", "POST", { lines }).catch(() => {});
    }, 700);
  }
  // Stop: the panel's ■ Stop reaches every frame; long loops check it between fields.
  let stopRequested = false;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ── answer matching ──────────────────────────────────────────────────────────────────────────────────────
  // Your answer and every option on the form are reduced to a meaning (yes / no / decline, f1 / h1b / gc, male, asian…)
  // and the option with the same meaning wins. So "F1", "F-1" and "F-1 Student" match "F-1 Student Visa (OPT)", and
  // "No", "Not a veteran" and "I am not a protected veteran" all pick "I am not a protected veteran".
  const low = (v) => (v ?? "").toString().replace(/[’‘]/g, "'").replace(/\s+/g, " ").trim().toLowerCase();
  const DECLINE = /decline|prefer not|rather not|choose not|don'?t wish|do not wish|wish not|not (?:wish|want|like) to|don'?t want to|do not want to|not to (?:answer|disclose|say|self)|undisclosed|not specified|no answer|no response|n\/a/;
  const NO = /^(?:no|n|nope|false|never|none)\b|^i(?: am|'m| do| will| have| can| would)?(?: not|n't)\b|^(?:not|don'?t|do not|will not|won'?t|cannot|can'?t|am not|have not|haven'?t)\b/;
  const YES = /^(?:yes|y|yeah|yep|true|sure|correct|absolutely|definitely)\b|^i(?: am|'m| do| will| have| can| would)\b/;
  const VISAS = [
    ["citizen", /\b(?:u\.?s\.?|united states|us) citizen|^citizen\b|citizenship\b(?!.*(?:not|non))/],
    ["gc", /green ?card|permanent resident|\blpr\b|\bi-?551\b/],
    ["f1", /\bf-?1\b|student visa|\bf ?1 student|\b(?:stem )?opt\b|\bcpt\b/],
    ["h1b", /\bh-?1-?b\b/], ["h4", /\bh-?4\b/], ["j1", /\bj-?1\b/], ["l1", /\bl-?1\b/], ["l2", /\bl-?2\b/],
    ["tn", /\btn\b/], ["o1", /\bo-?1\b/], ["e3", /\be-?3\b/], ["daca", /\bdaca\b/], ["asylum", /asyl|refugee/],
  ];
  const RACES = [
    ["two", /two or more|multi-?racial|mixed/], ["asian", /\basian\b|south asian|east asian|indian\b(?! american)/],
    ["black", /black|african/], ["pacific", /hawaiian|pacific island/],
    ["native", /american indian|alaska|native american|indigenous/], ["white", /\bwhite\b|caucasian/],
    ["hispanic", /hispanic|latin[oax]/], ["mena", /middle eastern|north african|\bmena\b/],
  ];

  const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  const DEGREES = [
    ["phd", /ph\.? ?d|doctor/], ["mba", /\bm\.?b\.?a\b|business administration/],
    ["master", /master|\bm\.?s\b|\bm\.?sc\b|\bm\.?eng\b|\bm\.?tech\b/],
    ["bachelor", /bachelor|undergrad|\bb\.?s\b|\bb\.?sc\b|\bb\.?e\b|\bb\.?tech\b|\bb\.?a\b/],
    ["associate", /associate/], ["highschool", /high school|secondary|\bged\b/],
  ];

  function meaning(kind, raw) {
    const t = low(raw);
    if (!t || t === "select..." || t === "select" || t === "--") return null;
    if (DECLINE.test(t)) return "decline";
    switch (kind) {
      case "yesno":
        return NO.test(t) ? "no" : YES.test(t) ? "yes" : null;
      case "veteran":
        if (/\bnot\b|^no\b|non-?veteran|never served|n't/.test(t)) return "no";
        return /veteran|^yes\b|served|military/.test(t) ? "yes" : meaning("yesno", t);
      case "disability":
        if (/^no\b|do not have|don'?t have|not have|without a disab|^none/.test(t)) return "no";
        return /^yes\b|have (?:had )?a disab|i have\b|disabled/.test(t) ? "yes" : meaning("yesno", t);
      case "gender":
        if (/non-?binary|genderqueer|gender non|agender|gender fluid/.test(t)) return "nonbinary";
        if (/\b(?:female|woman|women|girl)\b|^f$/.test(t)) return "female";
        return /\b(?:male|man|men|boy)\b|^m$/.test(t) ? "male" : null;
      case "race":
        return (RACES.find(([, re]) => re.test(t)) || [])[0] || null;
      case "visa":
        return (VISAS.find(([, re]) => re.test(t)) || [])[0] || null;
      case "month": {
        const n = t.match(/^0?(\d{1,2})$/);
        if (n) return +n[1] >= 1 && +n[1] <= 12 ? String(+n[1]) : null;
        const i = MONTHS.findIndex((m) => t.startsWith(m));
        return i >= 0 ? String(i + 1) : null;
      }
      case "degree":
        return (DEGREES.find(([, re]) => re.test(t)) || [])[0] || null;
      case "country": {
        // "United States", "USA", "US", "United States of America", "United States +1" are one country.
        const c = t.replace(/[^a-z .]+.*$/, "").replace(/\./g, "").replace(/^the /, "").trim();
        if (/^(us|usa|united states( of america)?|america)$/.test(c)) return "us";
        if (/^(uk|united kingdom|great britain|britain)$/.test(c)) return "uk";
        if (/^(uae|united arab emirates)$/.test(c)) return "uae";
        return c || null;
      }
    }
    return null;
  }

  const words = (s) => {
    const w = new Set(low(s).split(/[^a-z0-9]+/).filter((x) => x.length > 1));
    if (["indian", "pakistani", "bangladeshi", "nepali", "sri"].some((x) => w.has(x))) w.add("south");   // South Asian
    return w;
  };
  // The option for an answer: same meaning (ties broken by shared words), else exact / starts-with / contains text.
  function pick(options, answer, kind) {
    const real = options.filter((o) => meaning(kind || "text", o.text) !== null || low(o.text) && !/^select|^--/.test(low(o.text)));
    const want = kind ? meaning(kind, answer) : null;
    if (want) {
      const same = real.filter((o) => meaning(kind, o.text) === want);
      if (same.length) {
        const aw = words(answer);
        const ranked = same.map((o) => [o, [...words(o.text)].filter((w) => aw.has(w)).length])
          .sort((x, y) => y[1] - x[1]);
        // Two equally good options ("East Asian" / "South Asian" for "Asian"): ambiguous, leave it to you.
        if (ranked.length > 1 && ranked[0][1] === ranked[1][1] && kind === "race") return undefined;
        return ranked[0][0];
      }
      if (kind !== "text") return undefined;      // a yes/no question must never fall back to a text guess
    }
    const a = low(answer);
    const norm = real.map((o) => [o, low(o.text)]);
    return (norm.find(([, t]) => t === a) || norm.find(([, t]) => t.startsWith(a + " ") || t.startsWith(a + ","))
      || norm.find(([, t]) => a.length > 2 && t.includes(a)) || [])[0];
  }

  // What to type into a free-text box for a yes/no answer written any way in the profile.
  const asText = (kind, answer) =>
    kind === "yesno" ? ({ yes: "Yes", no: "No" }[meaning("yesno", answer)] || answer) : answer;
  // ── end answer matching ──────────────────────────────────────────────────────────────────────────────────────

  // ── field rules: label pattern → answer from the profile, and how to match it. First match wins. ──
  const SHORT = true;   // 4th entry: only for a short field label, not a question that mentions the word
  let phoneCodeField = false;      // set by fill(): the form has its own country phone code field
  const RULES = [
    // Compliance questions, first: their long labels mention "permanent resident", "Armed Services" and "employer".
    [/post-government employment restrictions/i, (p) => p.screening?.post_government_attest, "yesno"],
    [/(federal, state,? or local|u\.?s\.? federal) government|special government employee/i,
      (p) => p.screening?.government_employee, "yesno"],
    [/debar|declared ineligible/i, (p) => p.screening?.debarred, "yesno"],
    // "Unrestricted right to work" is No on any visa, unlike "authorized to work" (Yes on F-1).
    [/unrestricted (right|authori[sz]ation|eligibility) to work|without (any )?restrictions?\b[^?]{0,30}work/i,
      (p) => p.screening?.unrestricted_work, "yesno"],
    // "If you … require sponsorship, select your current visa type": the visa, not the yes/no sponsorship answer.
    [/(current|your) visa type|type of visa/i, (p) => p.work_authorization?.status, "visa"],
    [/enroll in a (postgraduate|graduate|further)|postgraduate degree|further (studies|education)/i,
      (p) => p.screening?.postgrad_after_internship, "yesno"],
    // "text" kind: these labels run long (an instruction before the question) but the answer is plain text.
    [/school location|location of (your )?(school|university|college)/i, (p) => p.education?.school_location, "text"],
    [/preferred location 1\b|(first|top) (choice )?(preferred )?location/i, (p) => p.screening?.preferred_locations?.[0], "text"],
    [/preferred location 2\b|second (choice )?(preferred )?location/i, (p) => p.screening?.preferred_locations?.[1]],
    [/preferred location 3\b|third (choice )?(preferred )?location/i, (p) => p.screening?.preferred_locations?.[2]],
    [/\biran\b|\bcuba\b|north korea|\bsyria\b|embargoed countr|sanctioned countr/i, (p) => p.screening?.sanctioned_country, "yesno"],
    [/future (positions|openings|opportunities|roles)|receive (communications|emails|updates)|talent (community|network|pool)/i,
      (p) => p.screening?.future_communications, "yesno"],
    // "Authorized to work … without (the need for) sponsorship?" is the opposite of "Will you need sponsorship?".
    [/without\b[^?.]{0,40}sponsor/i, (p) => {
      const need = meaning("yesno", p.work_authorization?.needs_sponsorship);
      const auth = meaning("yesno", p.work_authorization?.authorized_us);
      return need === "yes" ? "no" : need === "no" && auth === "yes" ? "yes" : "";
    }, "yesno"],
    [/sponsor/i, (p) => p.work_authorization?.needs_sponsorship, "yesno"],
    [/authori[sz]ed to work|legally (authori[sz]ed|eligible|permitted)|eligible to work|work authori[sz]ation|right to work/i,
      (p) => p.work_authorization?.authorized_us, "yesno"],
    [/visa|immigration status|citizenship status|work (authori[sz]ation|permit) (status|type)/i,
      (p) => p.work_authorization?.status, "visa"],
    [/hispanic|latin[oax]/i, (p) => p.eeo?.hispanic_latino, "yesno"],
    [/\bgender\b|\bsex\b/i, (p) => p.eeo?.gender, "gender"],
    [/\brace\b|ethnic/i, (p) => p.eeo?.race, "race"],
    [/veteran|military/i, (p) => p.eeo?.veteran, "veteran"],
    [/disabilit/i, (p) => p.eeo?.disability, "disability"],
    [/relocat/i, (p) => p.willing_to_relocate, "yesno"],
    [/how did you (hear|find|learn)|where did you (hear|find|learn)|referral source|^source$/i, (p) => p.how_did_you_hear],
    // Education dates (Greenhouse: "Start date month" / "End date year" under Education) before the job start date.
    [/^start (date )?month$/i, (p) => p.education?.start_month, "month"],
    [/^start (date )?year$/i, (p) => p.education?.start_year],
    [/^end (date )?month$/i, (p) => p.education?.graduation_month, "month"],
    [/^end (date )?year$/i, (p) => p.education?.graduation_year],
    [/start date|available to start|earliest (start|availability)|when can you start/i, (p) => p.earliest_start],
    [/preferred (first )?name|nickname/i, (p) => p.name?.preferred],
    [/first name|given name|legal first/i, (p) => p.name?.first],
    [/last name|family name|surname|legal last/i, (p) => p.name?.last],
    [/^(full |legal |your )?name\*?$|full name|legal name/i, (p) => [p.name?.first, p.name?.last].filter(Boolean).join(" ")],
    [/e-?mail/i, (p) => p.email],
    // Phone sub-fields: the device type is a dropdown, the extension and country code are not your number.
    [/phone (device )?type|type of phone/i, (p) => p.phone_type],
    [/extension|\bext\b|country (phone )?code|phone country|dialing code/i, () => ""],
    // With a separate country-code field (Workday), the number must be the national part only: "+1 …" is rejected.
    [/phone|mobile|cell/i, (p) => phoneCodeField ? String(p.phone || "").replace(/^\+\d{1,3}[\s-]*/, "") : p.phone],
    [/linkedin/i, (p) => p.links?.linkedin],
    [/github/i, (p) => p.links?.github],
    [/portfolio|personal (web)?site|^website/i, (p) => p.links?.portfolio],
    [/graduation (year)|grad(uation)? year|year of graduation/i, (p) => p.education?.graduation_year],
    [/graduation month/i, (p) => p.education?.graduation_month, "month"],
    [/graduat|expected (completion|degree date)|degree completion|complete (your |the )?(degree|program)|finish (your )?(degree|program)/i,
      (p) => p.education?.graduation],
    [/\bgpa\b|grade point/i, (p) => p.education?.gpa],
    [/school|universit|college|institution/i, (p) => p.education?.school, undefined, SHORT],
    [/major|field of study|discipline|area of study/i, (p) => p.education?.major, undefined, SHORT],
    [/degree/i, (p) => p.education?.degree, "degree", SHORT],
    [/current (or|\/) (most recent |previous )?employer|(current|most recent|previous) employer|current company/i,
      (p) => p.current_job?.employer],
    [/current (or|\/) (most recent |previous )?(job )?title|(current|most recent|previous) (job )?title/i,
      (p) => p.current_job?.title],
    [/country (where |in which )?you (currently )?(reside|live)|country of residence/i, (p) => p.location?.country, "country"],
    [/city and state|city, state|city\/state/i, (p) => [p.location?.city, p.location?.state].filter(Boolean).join(", ")],
    [/(currently )?enrolled in a (master'?s|graduate|degree)|current(ly)? (a )?(master'?s|graduate) student/i,
      (p) => p.education?.enrolled, "yesno"],
    [/address line 1|street address|address 1\b|^address\*?$|^street$/i, (p) => p.location?.address1],
    [/address line 2|address 2\b|\b(apt|suite|unit)\b/i, (p) => p.location?.address2],
    [/zip|postal/i, (p) => p.location?.zip],
    [/\bcity\b/i, (p) => p.location?.city, undefined, SHORT],
    [/\bstate\b|province|region/i, (p) => p.location?.state, undefined, SHORT],
    [/country/i, (p) => p.location?.country, "country", SHORT],
    [/current location|where are you (currently )?(based|located)|^location\*?$/i,
      (p) => [p.location?.city, p.location?.state].filter(Boolean).join(", ")],
  ];

  // Full dates (MM/DD/YYYY) for Workday's Month / Day / Year date questions.
  const DATE_RULES = [
    [/graduat|expected (completion|degree date)|degree completion/i, (p) => p.education?.graduation_date],
  ];

  const clean = (s) => (s || "").replace(/\s+/g, " ").replace(/[*✱]/g, "").trim();

  // The rule for a field. Essay boxes and long questions only get rules that know what they answer (kinded ones,
  // like sponsorship), never a profile value that merely shares a word ("degree" in "tell us about your degree").
  function ruleFor(label, el) {
    const essay = el instanceof HTMLTextAreaElement;
    return RULES.find(([re, , kind, short]) => re.test(label) &&
      !(short && (label.length > 40 || /\?$/.test(label))) && !(essay && (kind || label.length > 70)) &&
      (kind || label.length <= 90));
  }

  // The box holding one question: the most specific known wrapper first, a plain parent div last.
  const QUESTION_BOXES = ["fieldset", ".application-question", ".field", "[role='radiogroup']",
    "[data-automation-id^='formField']", ".ashby-application-form-field-entry", ".form-group", "li"];
  function questionBox(el) {
    for (const sel of QUESTION_BOXES) { const b = el.closest(sel); if (b) return b; }
    return el.parentElement?.closest("div");
  }
  const questionText = (box) =>
    clean((box?.querySelector("legend, .application-label, label:not(:has(input)), [class*='question-title']") || box)?.innerText || "");

  function labelOf(el) {
    const parts = [];
    if (el.labels && el.labels.length) parts.push(...[...el.labels].map((l) => l.innerText));
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    if (el.getAttribute("aria-label")) parts.push(el.getAttribute("aria-label"));
    if (!parts.length) {
      // Lever: .application-question > .application-label; Workday: [data-automation-id] containers; fieldsets.
      const q = questionText(questionBox(el));
      if (q && q.length < 200) parts.push(q);
    }
    if (!parts.length && el.placeholder) parts.push(el.placeholder);
    if (!parts.length) parts.push(el.name || el.id || "");
    // Greenhouse gives a field both a <label> and the same aria-label: keep each text once.
    return clean([...new Set(parts.map(clean).filter(Boolean))].join(" "));
  }

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  // Inputs a person never types into: react-select's invisible "requiredInput" (aria-hidden, tabindex -1).
  const helperInput = (el) => el.getAttribute("aria-hidden") === "true" || (el.tabIndex === -1 && !el.id && !el.name);

  function setValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);   // React tracks the native setter
    for (const t of ["input", "change", "blur"]) el.dispatchEvent(new Event(t, { bubbles: true }));
  }

  // green = from your profile, orange = needs you, blue = written by Claude (read it before submitting).
  function mark(el, ok) {
    // A dropdown is outlined on its visible control, not on react-select's tiny inner input box.
    const box = el.getAttribute("role") === "combobox"
      ? el.closest("[class*='__control'], [class*='-control']") || widgetOf(el) || el : el;
    box.style.outline = `2px solid ${ok === "ai" ? "#3b82f6" : ok ? "#22c55e" : "#f59e0b"}`;
    box.style.outlineOffset = "1px";
  }

  async function fillCombobox(el, answer, kind) {
    // react-select (Greenhouse questions): open the menu and click the option with the same meaning. Free-text
    // boxes (location autocomplete) get the answer typed first so the site can suggest options.
    for (const typed of kind ? [false] : [true, false]) {
      openCombobox(el);
      if (typed) { await sleep(150); setValue(el, answer); }
      for (let i = 0; i < (typed ? 30 : 15); i++) {       // searches (school, city) answer from the server
        await sleep(100);
        const hit = pick(comboOptions(el), answer, kind);
        if (hit) {
          hit.el.click();
          await sleep(150);
          if (!widgetOf(el)?.querySelector("[class*='__single-value'], [class*='singleValue'], [class*='multi-value']") &&
              widgetOf(el)?.querySelector("[class*='__control']")) { log(`  clicked "${clean(hit.text)}" but it did not stick; retrying`); break; }
          return true;
        }
      }
      closeCombobox(el);
    }
    return false;
  }
  // The whole select widget around a combobox input (its menu renders inside it). Tried in order: closest() with
  // one combined selector would stop at react-select's inner "input-container".
  function widgetOf(el) {
    for (const sel of [".select-shell", "[class*='select__container']", "[class*='select-container']"]) {
      const w = el.closest(sel); if (w) return w;
    }
    return el.closest("[class*='__control'], [class*='-control']")?.parentElement || null;
  }
  // Greenhouse's react-select opens on the mouse press AND release over its control (a press alone, or a focus,
  // does nothing); other comboboxes open on ArrowDown.
  function openCombobox(el) {
    if (el.getAttribute("aria-expanded") === "true") return;    // another press would close it again
    const control = el.closest("[class*='__control'], [class*='-control']") || el;
    el.focus();
    for (const t of ["mousedown", "mouseup", "click"]) {
      control.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, button: 0, view: window }));
    }
    if (el.getAttribute("aria-expanded") !== "true") {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", keyCode: 40, bubbles: true, cancelable: true }));
    }
  }
  function closeCombobox(el) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true, cancelable: true }));
    el.blur();
  }
  // The options of this combobox's open menu: its aria-controls listbox, else the menu inside its own widget.
  // Never the phone-country picker's 244 hidden options (intl-tel-input, .iti), which also use role=option.
  function comboOptions(el) {
    const listId = el?.getAttribute("aria-controls") || el?.getAttribute("aria-owns");
    const scope = (listId && document.getElementById(listId)) || (el && widgetOf(el)) || document;
    let opts = [...scope.querySelectorAll("[role='option'], [class*='__option']")];
    if (!opts.length && scope !== document) opts = [...document.querySelectorAll("[role='option']")];
    return opts.filter((o) => visible(o) && !o.closest(".iti"))
      .map((o) => ({ el: o, text: o.innerText }))
      .filter((o) => !/^(no options|loading|type to search|no results)/i.test(clean(o.text)));
  }

  // ── Workday "My Experience": a block per job and per school, filled from work_history / education_history ──
  // Blocks are matched to profile entries by company / school name (Workday pre-fills them from the resume), empty
  // blocks take the next unused entry, and "Add" makes more. Only empty fields are filled. Every field inside a block
  // is kept away from the general rules ("Location" or "School" there belongs to that job, not to you).
  const ENTRY = {
    work: { anchor: /^(job title|title|position)$/i, section: /work (experience|history)/i, list: (p) => p.work_history,
            key: "company", fields: [["title", /^(job title|title|position)$/i], ["company", /^(company|employer)/i],
            ["location", /^location/i], ["description", /description|responsibilit/i]] },
    edu: { anchor: /^(school|university|institution)( or university)?$/i, section: /^education/i, list: (p) => p.education_history,
           key: "school", fields: [["school", /^(school|university|institution)/i], ["degree", /^degree/i],
           ["field", /field of study|major|discipline/i], ["gpa", /gpa|grade average|overall result/i]] },
  };
  const entryFields = new WeakSet();       // inside a job / school block: never a question for Claude
  const isWorkday = () => /workday/i.test(location.host) || !!document.querySelector("[data-automation-id^='formField']");
  const titleOf = (field) => clean(field.querySelector("label, legend")?.innerText || "");

  // A block's labelled fields: Workday wraps each in data-automation-id="formField-…".
  const fieldsIn = (block) => [...block.querySelectorAll("[data-automation-id^='formField'], fieldset")]
    .filter((f) => !f.parentElement.closest("[data-automation-id^='formField'], fieldset") || !block.contains(f.parentElement.closest("[data-automation-id^='formField'], fieldset")));
  const fieldFor = (block, re) => fieldsIn(block).find((f) => re.test(titleOf(f)));

  function entryBlocks(kind) {
    const anchors = [...document.querySelectorAll("[data-automation-id^='formField'], fieldset")]
      .filter((f) => ENTRY[kind].anchor.test(titleOf(f)) && visible(f));
    return anchors.map((a) => {
      let box = a;
      // Grow to the whole block: stop at its own numbered heading ("Work Experience 2"), or before the section's
      // Add button or a second anchor comes in.
      const ownHeading = (el) => [...el.querySelectorAll("h2, h3, h4, h5, [role=heading]")].some((h) => /\d+\s*$/.test(clean(h.innerText)));
      while (!ownHeading(box) && box.parentElement && box.parentElement !== document.body &&
             anchors.filter((x) => box.parentElement.contains(x)).length === 1 &&
             ![...box.parentElement.querySelectorAll("button")].some((b) => /^add/i.test(clean(b.innerText || b.getAttribute("aria-label"))))) {
        box = box.parentElement;
      }
      return box;
    });
  }

  function addButton(kind) {
    return [...document.querySelectorAll("button")].filter(visible).find((b) => {
      const t = clean(b.innerText || "") + " " + (b.getAttribute("aria-label") || "");
      if (!/^add/i.test(t.trim())) return false;
      if (ENTRY[kind].section.test(t) && !/^add$/i.test(t.trim())) return true;
      // A bare "Add": the smallest ancestor with a heading tells which section it belongs to.
      for (let a = b.parentElement, i = 0; a && i < 6; a = a.parentElement, i++) {
        const h = a.querySelector("h2, h3, h4, [role=heading]");
        if (h) return ENTRY[kind].section.test(clean(h.innerText));
      }
      return false;
    });
  }

  // Workday's date spin inputs ignore a value written into the box (it shows, but Workday still says "required");
  // they only take typed text. insertText goes through the browser's editing path, like typing does.
  async function typeInto(el, text) {
    el.focus();
    el.select?.();
    const typed = document.execCommand && document.execCommand("insertText", false, text);
    if (!typed || el.value.replace(/\D/g, "") !== text.replace(/\D/g, "")) setValue(el, text);
    await sleep(60);
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  }
  // A box Workday has rejected, or one only written into earlier: enter it again.
  const needsEntry = (el, want) => !el.value || el.getAttribute("aria-invalid") === "true" ||
    !!el.closest("[data-automation-id^='formField']")?.querySelector("[data-automation-id='errorMessage'], [id*='error'][role='alert']") ||
    el.value.replace(/\D/g, "") !== String(want).replace(/\D/g, "");

  // Month/year date ("04/2026") or full date ("12/15/2027"): Workday splits it into Month (Day) Year spin inputs;
  // some forms have one box.
  async function fillDate(field, value) {
    const parts = String(value).split("/");
    const [mm, dd, yyyy] = parts.length === 3 ? parts : [parts[0], "", parts[1]];
    const inputs = [...field.querySelectorAll("input")].filter(visible);
    const named = (re) => inputs.find((i) => re.test(i.getAttribute("aria-label") + i.dataset.automationId + i.id));
    const month = named(/month/i), day = named(/day/i), year = named(/year/i);
    if (year) {                                     // education often asks for the year only
      if (month && needsEntry(month, mm)) await typeInto(month, mm);
      if (day && dd && needsEntry(day, dd)) await typeInto(day, dd);
      if (needsEntry(year, yyyy)) await typeInto(year, yyyy);
      log(`    date ${titleOf(field)}: month "${month?.value ?? "-"}" day "${day?.value ?? "-"}" year "${year.value}" invalid=${year.getAttribute("aria-invalid")}`);
      return !!year.value && year.getAttribute("aria-invalid") !== "true";
    }
    if (inputs.length === 1 && needsEntry(inputs[0], value)) { await typeInto(inputs[0], value); return true; }
    return inputs.some((i) => i.value);
  }

  // Workday's dropdown is a button that opens a listbox; its search boxes ("prompts") list matches after Enter.
  async function fillChoice(field, answer, kind) {
    const button = field.querySelector("button[aria-haspopup], button[data-automation-id]");
    const input = [...field.querySelectorAll("input")].find((i) => visible(i) && i.type !== "checkbox");
    if (button && (button.getAttribute("aria-haspopup") === "listbox" || !input)) {
      if (!/^(select one|select|choose)/i.test(clean(button.innerText))) return true;     // already chosen
      button.click();
    } else if (input) {
      if (field.querySelector("[data-automation-id='selectedItem'], [data-automation-id*='selectedItem']")) return true;
      input.focus(); setValue(input, answer);
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
    } else return false;
    for (let i = 0; i < 25; i++) {
      await sleep(150);
      const opts = [...document.querySelectorAll("[role='option'], [data-automation-id='promptOption']")].filter(visible)
        .map((o) => ({ el: o, text: clean(o.innerText) })).filter((o) => o.text);
      const hit = pick(opts, answer, kind);
      if (hit) { hit.el.click(); await sleep(200); return true; }
    }
    document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));
    return false;
  }

  async function fillEntry(kind, block, item) {
    let filled = 0, left = 0;
    const note = (ok, what) => { ok ? filled++ : left++; log(`  ${kind} "${item[ENTRY[kind].key]}": ${ok ? "filled" : "could not fill"} ${what}`); };
    for (const [key, re] of ENTRY[kind].fields) {
      const f = fieldFor(block, re), v = item[key];
      if (!f || !v) continue;
      const box = f.querySelector("textarea") || [...f.querySelectorAll("input")].find((i) => visible(i) && i.type !== "checkbox");
      const isChoice = f.querySelector("button[aria-haspopup]") || f.querySelector("[data-automation-id*='multiselect'], [data-automation-id*='prompt']");
      let ok;
      if (isChoice) ok = await fillChoice(f, v, key === "degree" ? "degree" : undefined);
      else if (box) { if (!box.value) setValue(box, v); ok = !!box.value; }
      else continue;
      mark(box || f, ok); note(ok, key);
    }
    if (kind === "work") {
      const cur = [...block.querySelectorAll("input[type=checkbox]")].find((c) => /currently work/i.test(labelOf(c) + " " + titleOf(c.closest("[data-automation-id^='formField'], fieldset") || block)));
      if (cur && cur.checked !== !item.to) { cur.click(); await sleep(200); }
    }
    for (const [key, re] of [["from", /^(from|start|first year)/i], ["to", /^(to|end|last year|graduat)/i]]) {
      const f = fieldFor(block, re);
      if (!f || !item[key] || !visible(f)) continue;
      const ok = await fillDate(f, item[key]); mark(f, ok); note(ok, key);
    }
    return { filled, left };
  }

  async function fillEntries(profile, done) {
    let filled = 0, left = 0;
    if (!isWorkday()) return { filled, left };
    for (const kind of ["work", "edu"]) {
      const items = (ENTRY[kind].list(profile) || []).filter(Boolean);
      if (!items.length) continue;
      let blocks = entryBlocks(kind);
      if (!blocks.length && !addButton(kind)) continue;                 // this page has no such section
      log(`${kind === "work" ? "Work experience" : "Education"}: ${blocks.length} block(s) on the page, ${items.length} in your profile`);
      // The block's structure goes to the log, so a Workday variant that does not fill can be fixed from it.
      if (blocks[0]) log(`  fields: ${fieldsIn(blocks[0]).map((f) => `${titleOf(f)} [${f.dataset.automationId || f.tagName}: ${
        [...f.querySelectorAll("input, textarea, button")].map((i) => i.tagName.toLowerCase() + (i.type ? ":" + i.type : "") +
        (i.dataset.automationId ? "#" + i.dataset.automationId : "")).join(" ")}]`).join(" | ").slice(0, 1500)}`);
      const used = new Set();
      const keyOf = (b) => { const f = fieldFor(b, ENTRY[kind].fields.find(([k]) => k === ENTRY[kind].key)[1]);
        return low(f?.querySelector("input")?.value || f?.querySelector("button")?.innerText || ""); };
      const plan = [];
      for (const b of blocks) {                                         // a pre-filled block keeps its own entry
        const k = keyOf(b);
        const i = k ? items.findIndex((it, j) => !used.has(j) && (low(it[ENTRY[kind].key]).includes(k) || k.includes(low(it[ENTRY[kind].key])))) : -1;
        if (i >= 0) { used.add(i); plan.push([b, items[i]]); } else plan.push([b, null]);
      }
      for (const p of plan) if (!p[1]) { const i = items.findIndex((_, j) => !used.has(j)); if (i >= 0) { used.add(i); p[1] = items[i]; } }
      // More entries than blocks: Add, then fill the new block.
      for (let i = items.findIndex((_, j) => !used.has(j)); i >= 0 && !stopRequested; i = items.findIndex((_, j) => !used.has(j))) {
        const add = addButton(kind);
        if (!add) { log(`  no Add button for ${kind}; ${items.length - used.size} entr(ies) left for you`); break; }
        const before = entryBlocks(kind);
        add.click();
        let fresh = null;
        for (let t = 0; t < 20 && !fresh; t++) { await sleep(150); fresh = entryBlocks(kind).find((b) => !before.includes(b) && !plan.some(([x]) => x === b)); }
        if (!fresh) { log(`  clicked Add for ${kind} but no new block appeared`); break; }
        used.add(i); plan.push([fresh, items[i]]);
      }
      for (const [block, item] of plan) {
        block.querySelectorAll("input, textarea, select, button").forEach((el) => { done.add(el); entryFields.add(el); });
        if (!item || stopRequested) continue;
        progress(`${kind === "work" ? "Work experience" : "Education"}: ${item[ENTRY[kind].key]}`);
        const r = await fillEntry(kind, block, item);
        filled += r.filled; left += r.left;
      }
    }
    return { filled, left };
  }

  async function fill(profile) {
    stopRequested = false;
    let filled = 0, left = 0;
    const done = new Set();
    try {
      const r = await fillEntries(profile, done);
      filled += r.filled; left += r.left;
    } catch (e) { log(`work/education blocks failed: ${e}`); }
    // Radio groups first (yes/no questions), one answer per group.
    const groups = {};
    document.querySelectorAll("input[type=radio]").forEach((r) => { (groups[r.name] ||= []).push(r); });
    for (const radios of Object.values(groups)) {
      if (!radios.some(visible) || radios.some((r) => r.checked)) continue;
      const box = questionBox(radios[0]);
      const q = questionText(box);
      const rule = ruleFor(q, radios[0]);
      const answer = rule && rule[1](profile);
      if (!answer) {
        radios.forEach((r) => done.add(r));
        if (rule && radios.some((r) => r.required)) { mark(box, false); left++; }
        continue;
      }
      const hit = pick(radios.map((r) => ({ el: r, text: labelOf(r) })), answer, rule[2]);
      if (hit) { hit.el.click(); mark(box, true); filled++; } else { mark(box, false); left++; }
      radios.forEach((r) => done.add(r));
    }
    phoneCodeField = [...document.querySelectorAll("label, legend")].some((l) => /country (phone )?code|phone country/i.test(l.innerText));
    // Workday's dropdowns are buttons ("Select One") inside a labelled formField, not inputs.
    const pending = () => [...document.querySelectorAll("input, textarea, select, [data-automation-id^='formField'] button[aria-haspopup='listbox']")].filter((el) =>
      visible(el) && !done.has(el) && !el.disabled && !el.readOnly && !helperInput(el) &&
      (el.tagName === "BUTTON" || !["hidden", "file", "submit", "button", "checkbox", "radio", "search"].includes(el.type)));
    // Answers can reveal follow-up questions (Greenhouse asks race only after "Hispanic/Latino? No"), so the form is
    // scanned again for fields that appeared while filling.
    for (let pass = 0, fields = pending(); pass < 3 && fields.length; pass++, await sleep(300), fields = pending()) {
    for (const [i, el] of fields.entries()) {
      done.add(el);
      if (stopRequested) { progress(`Stopped at field ${i + 1} of ${fields.length}.`); break; }
      // A Workday date question is Month / Day / Year spin boxes under one label: filled together, never one by one.
      const dateField = el.tagName === "INPUT" && el.closest("[data-automation-id^='formField']");
      if (dateField?.querySelector("[data-automation-id*='dateSection']")) {
        dateField.querySelectorAll("input").forEach((x) => done.add(x));
        const title = titleOf(dateField), date = DATE_RULES.find(([re]) => re.test(title))?.[1](profile);
        if (!date) { if (/\*/.test(title) && !el.value) { mark(dateField, false); left++; } continue; }
        const ok = await fillDate(dateField, date);
        mark(dateField, ok); ok ? filled++ : left++;
        log(`  ${ok ? "filled" : "could not fill"} date "${title.slice(0, 60)}" with "${date}"`);
        continue;
      }
      const wdField = el.tagName === "BUTTON" && el.closest("[data-automation-id^='formField']");
      const label = wdField ? titleOf(wdField) : labelOf(el);
      progress(`Filling ${i + 1} of ${fields.length}: ${label.slice(0, 60)}`);
      const t0 = Date.now();
      const rule = ruleFor(label, el);
      const required = el.required || el.getAttribute("aria-required") === "true" || /\*/.test(label);
      if (!rule) { if (required && !el.value) { mark(el, false); left++; } continue; }
      const answer = rule[1](profile);
      const isCombo = el.getAttribute("role") === "combobox";
      const combo = isCombo && widgetOf(el);
      const placeholder = (o) => !o || !o.value || /^(select|choose|please select|--|—|-)\b|^\s*$/i.test(o.text.trim());
      const hasValue = wdField ? !/^(select one|select|choose)/i.test(clean(el.innerText))
        : isCombo ? !!combo?.querySelector("[class*='singleValue'], [class*='single-value']")
        : el instanceof HTMLSelectElement ? !placeholder(el.options[el.selectedIndex]) : !!el.value;
      if (hasValue) continue;                                    // never overwrite what is already there
      if (!answer) { if (required) { mark(el, false); left++; } continue; }
      let ok = false;
      if (wdField) {
        ok = await fillChoice(wdField, answer, rule[2]);
      } else if (el instanceof HTMLSelectElement) {
        const opt = pick([...el.options].map((o) => ({ el: o, text: o.text })), answer, rule[2]);
        if (opt) { setValue(el, opt.el.value); ok = true; }
      } else if (isCombo) {
        ok = await fillCombobox(el, answer, rule[2]);
      } else {
        setValue(el, asText(rule[2], answer)); ok = true;
      }
      mark(el, ok);
      ok ? filled++ : left++;
      log(`  ${ok ? "filled" : "could not fill"} "${label.slice(0, 60)}" with "${String(answer).slice(0, 40)}" ` +
          `(${isCombo || wdField ? "dropdown" : el.tagName.toLowerCase()}, ${Date.now() - t0} ms)`);
    }
    }
    return { filled, left };
  }

  // ── questions for Claude: what is still empty after Fill and is not something your profile owns ─────────
  // Never sent: anything a profile rule covers (an empty profile answer means "leave it to me"), pay, identity
  // numbers, signatures, consent boxes.
  const NEVER_AI = /salary|compensation|pay (range|expectation)|desired pay|\bssn\b|social security|date of birth|birthday|password|signature|sign here|today'?s date|consent|i (agree|acknowledge|certify)/i;
  const qState = new Map();     // key → { el(s), type, options }

  // The most a form allows, from a stated limit like "max 500 characters", "200-300 words" or "in 150 words or less"
  // ("at least / minimum N" is skipped). 0 = none stated.
  function statedMax(text, unit) {
    const re = new RegExp(`(at least|min(?:imum)?(?: of)?)?\\s*(\\d[\\d,]*)\\s*(?:-|–|to)?\\s*(\\d[\\d,]*)?\\s*${unit}`, "ig");
    let best = 0;
    for (const m of text.matchAll(re)) {
      if (m[1]) continue;
      const n = parseInt((m[3] || m[2]).replace(/,/g, ""), 10);
      if (n > 0 && (!best || n < best)) best = n;
    }
    return best;
  }

  // A text field's length limits: its maxlength, a limit stated in the label or help text, or a "0/500" counter.
  function limitsOf(el, text) {
    const chars = [el.maxLength > 0 && el.maxLength < 100000 ? el.maxLength : 0,
                   statedMax(text, "(?:characters?|chars?)\\b"),
                   +((text.match(/\b0\s*\/\s*(\d{2,5})\b/) || [])[1] || 0)].filter(Boolean);
    return { max_length: chars.length ? Math.min(...chars) : undefined, max_words: statedMax(text, "words?\\b") || undefined };
  }

  // Cut an answer down to the limits at a sentence end (else a word end). Returns [text, wasCut].
  function fitTo(answer, { max_length, max_words } = {}) {
    const full = String(answer);
    let t = full;
    if (max_words) { const w = t.trim().split(/\s+/); if (w.length > max_words) t = w.slice(0, max_words).join(" "); }
    if (max_length && t.length > max_length) t = t.slice(0, max_length);
    if (t === full) return [full, false];
    const sentence = t.match(/^[\s\S]*[.!?](?=\s|$)/);
    t = sentence && sentence[0].length >= t.length / 2 ? sentence[0] : t.replace(/\s+\S*$/, "");
    return [t.trim(), true];
  }

  async function collectQuestions() {
    const out = [];
    qState.clear();
    const add = (q, ref) => { q.key = "q" + out.length; qState.set(q.key, { ...ref, type: q.type, options: q.options }); out.push(q); };
    const helpOf = (el, box) => {
      const ids = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
      const t = ids.map((id) => document.getElementById(id)?.innerText || "").join(" ");
      return clean(t || (box?.innerText || "")).slice(0, 600);
    };
    const groups = {};
    document.querySelectorAll("input[type=radio]").forEach((r) => { (groups[r.name] ||= []).push(r); });
    const seen = new Set();
    for (const radios of Object.values(groups)) {
      radios.forEach((r) => seen.add(r));
      if (!radios.some(visible) || radios.some((r) => r.checked)) continue;
      const box = questionBox(radios[0]);
      const label = questionText(box);
      if (!label || ruleFor(label, radios[0]) || NEVER_AI.test(label)) continue;
      add({ label: label.slice(0, 400), type: "choice", options: radios.map(labelOf),
            required: radios.some((r) => r.required) }, { radios });
    }
    for (const el of document.querySelectorAll("input, textarea, select")) {
      if (seen.has(el) || entryFields.has(el) || !visible(el) || el.disabled || el.readOnly || helperInput(el) ||
          ["hidden", "file", "submit", "button", "checkbox", "radio", "search"].includes(el.type)) continue;
      if (stopRequested) break;
      const label = labelOf(el);
      if (!label || ruleFor(label, el) || NEVER_AI.test(label)) continue;
      progress(`Reading question: ${label.slice(0, 60)}`);
      const required = el.required || el.getAttribute("aria-required") === "true";
      const isCombo = el.getAttribute("role") === "combobox";
      const box = questionBox(el);
      const help = helpOf(el, null);
      if (el instanceof HTMLSelectElement) {
        const placeholder = (o) => !o.value || /^(select|choose|please select|--)/i.test(o.text.trim());
        if (!placeholder(el.options[el.selectedIndex] || { value: "", text: "" })) continue;
        add({ label, help, type: "choice", required, options: [...el.options].filter((o) => !placeholder(o)).map((o) => o.text.trim()) }, { el });
      } else if (isCombo) {
        const shell = widgetOf(el);
        if (shell?.querySelector("[class*='singleValue'], [class*='single-value'], [class*='multiValue'], [class*='multi-value']")) continue;
        // Read the option list: open the menu, collect, close. No list until you type = a search box.
        openCombobox(el);
        let options = [];
        for (let i = 0; i < 12 && !options.length; i++) {      // Greenhouse loads some lists when opened
          await sleep(150);
          options = comboOptions(el).map((o) => clean(o.text)).slice(0, 150);
        }
        closeCombobox(el);
        add(options.length ? { label, help, type: "choice", required, options } : { label, help, type: "search", required }, { el });
      } else {
        if (el.value) continue;
        const lim = limitsOf(el, [label, help, (box?.innerText || "").slice(0, 1500)].join(" "));
        add({ label, help, required, type: el instanceof HTMLTextAreaElement ? "long_text" : "short_text", ...lim },
            { el, lim });
      }
    }
    return out;
  }

  async function applyAnswers(answers) {
    let filled = 0;
    for (const { key, answer } of answers || []) {
      const q = qState.get(key);
      if (!q || answer == null || answer === "") continue;
      let ok = false;
      if (q.radios) {
        const hit = pick(q.radios.map((r) => ({ el: r, text: labelOf(r) })), String(answer));
        if (hit) { hit.el.click(); mark(questionBox(q.radios[0]), "ai"); ok = true; }
      } else if (q.el instanceof HTMLSelectElement) {
        const hit = pick([...q.el.options].map((o) => ({ el: o, text: o.text })), String(answer));
        if (hit) { setValue(q.el, hit.el.value); ok = true; }
      } else if (q.el.getAttribute("role") === "combobox") {
        // A known option list is picked from the opened menu; only search boxes get the answer typed.
        ok = await fillCombobox(q.el, String(answer), q.type === "choice" ? "text" : undefined);
      } else if (!q.el.value) {
        // Claude is told the limit; this is the guard for when it goes over (a form would reject or cut it).
        const [text, cut] = fitTo(answer, q.lim);
        setValue(q.el, text);
        if (cut) {
          log(`answers: "${key}" was ${String(answer).length} chars / ${String(answer).trim().split(/\s+/).length} words, ` +
              `over the limit ${JSON.stringify(q.lim)}; cut to ${text.length} chars at a sentence end`);
          mark(q.el, false); filled++; continue;    // orange: shortened, read it
        }
        ok = true;
      }
      if (ok) { if (!q.radios) mark(q.el, "ai"); filled++; }
    }
    return filled;
  }

  // Runs in the frame that holds the form: send the open questions to Claude (through the helper), wait, fill.
  async function aiHere(info, onDone) {
    stopRequested = false;
    const questions = await collectQuestions();
    if (stopRequested) return { error: "Stopped." };
    log(`sending ${questions.length} question(s) to Claude: ${questions.map((q) => q.label.slice(0, 40)).join(" | ")}`);
    if (!questions.length) return { count: 0 };
    const job = info?.found ? info.job.id : null;
    const start = await api("/api/answers", "POST", { job_id: job, url: location.href, referrer: document.referrer,
                                                      page_title: document.title, questions });
    if (!start || !start.run_id) return { error: start?.error || "helper-offline" };
    (async () => {
      for (let i = 0; i < 100; i++) {             // up to ~8 minutes
        await sleep(5000);
        if (stopRequested) { log("answers: stopped before filling"); return; }
        const r = await api(`/api/answers/${start.run_id}`);
        if (r?.status === "running") continue;
        log(`answers: ${r?.status} ${r?.error || ""}`);
        const filled = r?.status === "done" ? await applyAnswers(r.answers) : 0;
        log(`answers: filled ${filled}`);
        onDone && onDone({ ...r, filled });
        return;
      }
    })();
    return { count: questions.length, run_id: start.run_id };
  }

  async function attach(input, path) {
    const f = await send({ type: "file", path });
    if (!f || f.error) return false;
    const bytes = Uint8Array.from(atob(f.base64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], f.name, { type: f.type }));
    input.files = dt.files;
    for (const t of ["input", "change"]) input.dispatchEvent(new Event(t, { bubbles: true }));
    return f.name;
  }

  function fileKind(input) {
    const t = `${labelOf(input)} ${input.name} ${input.id} ${input.closest("div")?.innerText?.slice(0, 120) || ""}`;
    if (/cover/i.test(t)) return "cover";
    if (/resume|r[ée]sum[ée]|\bcv\b/i.test(t)) return "resume";
    return null;
  }

  async function attachFiles(info) {
    const notes = [];
    // The panel's match, else this frame's own (an embedded form matches by its referrer, the company job page).
    const found = info.found ? info : state.info?.found ? state.info : null;
    const jobId = found ? found.job.id : "none";
    log(`attach: job ${jobId}${found ? "" : " (no matching job: the default resume)"}`);
    for (const input of document.querySelectorAll("input[type=file]")) {
      if (input.files && input.files.length) continue;
      const kind = fileKind(input);
      if (kind === "resume" && (found || info).resume?.available) {
        const name = await attach(input, `/api/file/resume/${jobId}`);
        if (name) notes.push(`📄 ${name}`);
        log(`attach: resume ${name || "failed"}`);
      } else if (kind === "cover" && found?.cover_letter?.available) {
        const name = await attach(input, `/api/file/cover/${jobId}`);
        if (name) notes.push(`✉️ ${name}`);
      }
    }
    // Cover letter as a text box (some forms have no upload for it).
    if (info.cover_letter?.text) {
      for (const ta of document.querySelectorAll("textarea")) {
        if (visible(ta) && !ta.value && /cover letter/i.test(labelOf(ta))) {
          setValue(ta, info.cover_letter.text); mark(ta, true); notes.push("✉️ pasted cover letter");
        }
      }
    }
    return notes;
  }

  // ── "applied" detection: after a submit click, watch for the site's confirmation ─────────────
  const CONFIRM = /thank(s| you) for (applying|your (application|interest))|application (has been |was )?(received|submitted)|we('ve| have) received your application|successfully (submitted|applied)/i;
  const PENDING_KEY = "jobAlertsPendingApply";

  async function markApplied(jobId, why) {
    const r = await api("/api/status", "POST", { job_id: jobId, status: "applied" });
    sessionStorage.removeItem(PENDING_KEY);
    setStatus(r && r.ok ? `✅ Marked as applied (${why})` : "Could not reach the helper to mark it applied");
    if (r && r.ok && state.info) state.info.status = "applied";
    render();
  }

  function watchSubmit() {
    document.addEventListener("click", (e) => {
      const b = e.target.closest("button, input[type=submit], a[role=button]");
      if (!b || !state.info?.found) return;
      const t = clean(b.innerText || b.value || "");
      if (!(b.type === "submit" || /submit|send application|apply/i.test(t)) || /save|next|back|cancel/i.test(t)) return;
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ id: state.info.job.id, at: Date.now() }));
      let tries = 0;
      const timer = setInterval(() => {
        if (CONFIRM.test(document.body.innerText)) { clearInterval(timer); markApplied(state.info.job.id, "confirmation seen"); }
        if (++tries > 40) clearInterval(timer);
      }, 500);
    }, true);
    // The confirmation may be a new page in the same tab.
    const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || "null");
    if (pending && Date.now() - pending.at < 10 * 60 * 1000 && CONFIRM.test(document.body.innerText)) {
      markApplied(pending.id, "confirmation seen");
    }
  }

  // ── panel ─────────────────────────────────────────────────────────────
  const state = { info: null, profile: null, status: "", shown: false };
  let root;

  function setStatus(s) { state.status = s; render(); }

  function render() {
    if (!root) return;
    const i = state.info;
    const job = i?.found ? `<b>${esc(i.job.company)}</b> · ${esc(i.job.title)} <span class=dim>#${i.job.id}</span>`
      : i?.error ? `<span class=warn>${esc(errorText(i.error))}</span>` : `<span class=dim>Not one of your alerts (fills the form anyway)</span>`;
    const st = i?.status ? `<div>Status: <b>${{ applied: "✅ Applied", later: "⭐ Later", skip: "⏭ Skipped" }[i.status]}</b></div>` : "";
    const res = i?.resume?.available ? `📄 ${i.resume.tailored ? "Tailored" : "Default"} resume: ${esc(i.resume.name || "")}`
      : "📄 No resume (set default_resume in profile.yaml)";
    const cov = i?.cover_letter?.available ? `✉️ Cover letter ready` : i?.cover_letter?.generating ? "✉️ Writing cover letter…" : "";
    root.innerHTML = `
      <style>
        .box{position:fixed;${state.pos ? `left:${state.pos.left}px;top:${state.pos.top}px` : `right:16px;${window.top !== window ? "top" : "bottom"}:16px`};
             z-index:2147483647;width:${state.collapsed ? "auto;max-width:300px" : "300px"};background:#111827;color:#f9fafb;
             font:13px/1.4 system-ui,sans-serif;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.35);padding:12px}
        .head{display:flex;align-items:center;gap:8px;cursor:move;user-select:none;margin:-12px -12px 0;padding:10px 12px}
        .head b{flex:1} .ic{cursor:pointer;color:#9ca3af;padding:0 3px} .ic:hover{color:#f9fafb}
        .mini{font-size:11px;color:#9ca3af;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .row{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
        button{all:unset;cursor:pointer;background:#374151;padding:5px 9px;border-radius:6px;font-size:12px}
        button.primary{background:#16a34a} button:hover{filter:brightness(1.2)}
        .dim{color:#9ca3af} .warn{color:#fbbf24} .x{float:right;cursor:pointer;color:#9ca3af}
        .msg{margin-top:8px;color:#d1d5db;font-size:12px}
      </style>
      <div class=box>
        <div class=head id=ja-head title="Drag to move">
          <b>Job Alerts</b>${state.collapsed && state.busy ? `<span class=mini>${esc(state.status)}</span>` : ""}
          <span class=ic id=ja-collapse title="${state.collapsed ? "Expand" : "Collapse"}">${state.collapsed ? "▢" : "–"}</span>
          <span class=ic id=ja-close title="Close">✕</span>
        </div>
        ${state.collapsed ? "" : `
        <div style="margin-top:2px">${job}</div>${st}
        <div class=dim style="margin-top:4px">${res}${cov ? "<br>" + cov : ""}</div>
        <div class=row>
          <button class=primary id=ja-fill>Fill form</button>
          <button id=ja-ai title="Claude drafts answers for the questions Fill left empty">✍️ Answer the rest</button>
          ${state.busy ? `<button id=ja-stop>■ Stop</button>` : ""}
          ${i?.found ? `<button id=ja-applied>✅ Applied</button><button id=ja-later>⭐ Later</button><button id=ja-skip>⏭ Skip</button>` : ""}
        </div>
        ${i?.found ? `<div class=row>
          ${i.resume?.tailored ? "" : `<button id=ja-make-resume>${i.resume?.generating ? "Writing resume…" : "Make tailored resume"}</button>`}
          ${i.cover_letter?.available ? "" : `<button id=ja-make-cover>${i.cover_letter?.generating ? "Writing letter…" : "Make cover letter"}</button>`}
        </div>` : ""}
        <div class=msg>${esc(state.status)}</div>`}
      </div>`;
    const on = (id, f) => { const b = root.getElementById(id); if (b) b.onclick = f; };
    on("ja-close", () => { root.host.remove(); root = null; });
    on("ja-collapse", () => { state.collapsed = !state.collapsed; savePanel(); render(); });
    drag(root.getElementById("ja-head"), root.querySelector(".box"));
    on("ja-fill", runFill);
    on("ja-ai", runAI);
    on("ja-stop", stopAll);
    for (const s of ["applied", "later", "skip"]) on(`ja-${s}`, () => setJobStatus(s));
    on("ja-make-resume", () => generate("resume"));
    on("ja-make-cover", () => generate("cover"));
  }

  // The panel can be dragged by its title bar and collapsed to the bar; where it sits and whether it is collapsed
  // is remembered for every site.
  function drag(handle, box) {
    if (!handle) return;
    handle.onpointerdown = (e) => {
      if (e.target.closest(".ic")) return;
      const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      handle.setPointerCapture(e.pointerId);
      handle.onpointermove = (m) => {
        const left = Math.min(Math.max(0, m.clientX - dx), innerWidth - r.width);
        const top = Math.min(Math.max(0, m.clientY - dy), innerHeight - 40);
        Object.assign(box.style, { left: left + "px", top: top + "px", right: "auto", bottom: "auto" });
        state.pos = { left: Math.round(left), top: Math.round(top) };
      };
      handle.onpointerup = () => { handle.onpointermove = handle.onpointerup = null; savePanel(); };
    };
  }
  function savePanel() {
    try { chrome.storage?.local.set({ panel: { pos: state.pos || null, collapsed: !!state.collapsed } }); } catch (_) { /* tests */ }
  }
  async function restorePanel() {
    try {
      const { panel } = await chrome.storage.local.get({ panel: null });
      if (!panel) return;
      // A position from a wider window could be off-screen here: keep it inside the viewport.
      if (panel.pos) state.pos = { left: Math.min(panel.pos.left, innerWidth - 320), top: Math.min(panel.pos.top, innerHeight - 60) };
      state.collapsed = !!panel.collapsed;
    } catch (_) { /* tests */ }
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const errorText = (e) => ({ "no-token": "Set the helper token in the extension options",
    "bad-token": "Wrong helper token (extension options)", "helper-offline": "Helper offline: start `python -m jobalerts bot`" }[e] || e);

  async function load() {
    const urls = [location.href, document.referrer].filter(Boolean).map((u) => "url=" + encodeURIComponent(u)).join("&");
    state.info = await api(`/api/match?${urls}`);
    render();
  }

  function stopAll() {
    stopRequested = true;
    state.stopped = true;
    if (!window.__jobAlertsTestSend) send({ type: "stop-all" }).catch(() => {});
    state.busy = false;
    setStatus("Stopping… (anything already filled stays; reload the page to clear it)");
  }
  const busy = async (f) => { state.busy = true; state.stopped = false; render();
    try { await f(); } finally { state.busy = false; render(); } };

  const withTimeout = (p, ms) => Promise.race([p, sleep(ms).then(() => ({ error: "timeout" }))]);

  const runFill = () => busy(runFillInner);
  async function runFillInner() {
    setStatus("Filling…");
    state.profile = state.profile || await api("/api/profile");
    if (!state.profile || state.profile.error) { setStatus(errorText(state.profile?.error || "helper-offline")); return; }
    // Fill every frame of the tab (the form is often an iframe inside the company's page); tests have only this one.
    let r = window.__jobAlertsTestSend ? null
      : await withTimeout(send({ type: "fill-all", profile: state.profile, info: state.info || {} }), 120000);
    if (r?.error === "timeout") { setStatus("Fill is taking over 2 minutes; something is stuck. Reload the page and try again, and tell Claude which field it stopped at."); return; }
    if (!r || r.error) r = await fillHere(state.profile, state.info || {});
    const { filled, left, notes } = r;
    if (!filled && !left && !notes.length) {
      setStatus("No application form found on this page. Open the job's Apply page (the one with the fields), then Fill.");
      return;
    }
    setStatus(`Filled ${filled} field(s)${notes.length ? ", attached " + notes.join(", ") : ""}. ` +
      (left ? `${left} highlighted in orange need you.` : "Check everything, then submit."));
  }

  // Claude answers what Fill left empty. The form may be in another frame: that frame collects the questions and
  // fills the answers; this panel only follows the run on the helper.
  const runAI = () => busy(runAIInner);
  async function runAIInner() {
    setStatus("Reading the open questions…");
    let r = window.__jobAlertsTestSend ? null : await send({ type: "ai-all", info: state.info || {} });
    if (!r || r.error === "frames") r = await aiHere(state.info || {});
    if (r.error) { setStatus(errorText(r.error)); return; }
    if (!r.count) { setStatus("No open questions left for Claude (fields your profile covers are yours to fill)."); return; }
    setStatus(`Answering ${r.count} question(s) from your experience bank (Claude; a minute or two)…`);
    for (let i = 0; i < 100; i++) {
      await sleep(5000);
      if (state.stopped) return;
      const s = await api(`/api/answers/${r.run_id}`);
      if (s?.status === "running") continue;
      if (s?.status !== "done") { setStatus(`Claude could not answer: ${s?.error || "unknown error"}`); return; }
      const n = (s.answers || []).filter((a) => a.answer != null && a.answer !== "").length;
      await sleep(3000);                          // the form's frame fills them in meanwhile
      setStatus(`${s.provider || "Claude"} answered ${n} of ${r.count}; they are outlined in blue. Read and edit each one before ` +
        `submitting.${s.notes ? " Note: " + s.notes : ""}` +
        (s.usage ? ` (${((s.usage.input + s.usage.cached + s.usage.output) / 1000).toFixed(0)}k tokens, ${s.usage.seconds}s)` : ""));
      return;
    }
  }

  async function setJobStatus(s) {
    const next = state.info.status === s ? "none" : s;
    const r = await api("/api/status", "POST", { job_id: state.info.job.id, status: next });
    if (r?.ok) { state.info.status = next === "none" ? null : next; setStatus("Saved; the Discord alert is updated too."); }
  }

  async function generate(kind) {
    await api("/api/generate", "POST", { job_id: state.info.job.id, kind });
    setStatus(`Writing the ${kind === "cover" ? "cover letter" : "resume"} (a few minutes). This panel updates when it is ready.`);
    for (let i = 0; i < 90; i++) {                // poll up to ~15 minutes
      await sleep(10000);
      await load();
      const part = kind === "cover" ? state.info.cover_letter : state.info.resume;
      if (kind === "cover" ? part?.available : part?.tailored) { setStatus("Ready. Press Fill form to attach it."); return; }
      if (part && !part.generating) { setStatus("Generation finished without a file; check Discord or the job folder."); return; }
    }
  }

  function looksLikeApplication() {
    return !!document.querySelector("input[type=file], input[type=email], input[name*=email i], [data-automation-id*='email' i]");
  }

  async function fillHere(profile, info) {
    const { filled, left } = await fill(profile);
    return { filled, left, notes: await attachFiles(info) };
  }

  async function show(force) {
    if (root || state.shown) { if (root) render(); return; }
    if (!force && !looksLikeApplication()) return;
    state.shown = true;
    const inFrame = window.top !== window;
    if (inFrame) {
      await load();                                // the job, for Fill and for the "applied" detection here
      // Put the panel on the outer page where it is visible; if that is not allowed, show it in this frame.
      // (The toolbar button already shows one there.)
      if (force) return;
      if (!window.__jobAlertsTestSend) {
        const r = await send({ type: "show-top" }).catch(() => null);
        if (r && r.ok) return;
      }
    }
    const host = document.createElement("div");
    document.documentElement.appendChild(host);
    root = host.attachShadow({ mode: "open" });
    await restorePanel();
    render();
    if (!state.info) await load();
  }

  window.__jobAlertsShow = show;
  window.__jobAlertsFillHere = fillHere;
  // The panel may be on the outer page while the form is in this frame: only a frame with a form answers.
  if (!window.__jobAlertsTestSend && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
      if (msg.type === "progress") { if (root && !state.stopped) setStatus(msg.text); return false; }
      if (msg.type === "stop") { stopRequested = true; return false; }
      if (!["fill-here", "ai-here"].includes(msg.type) || !looksLikeApplication()) return false;
      (msg.type === "fill-here" ? fillHere(msg.profile, msg.info) : aiHere(msg.info)).then(reply, () => reply(null));
      return true;
    });
  }
  window.__jobAlertsFill = fill;     // for tests
  window.__jobAlertsCollect = collectQuestions;
  window.__jobAlertsCombo = { fill: fillCombobox, options: comboOptions, open: openCombobox };
  window.__jobAlertsLimits = (el, text) => limitsOf(el, text);
  window.__jobAlertsFit = fitTo;
  window.__jobAlertsApplyAnswers = applyAnswers;
  window.__jobAlertsAttach = attachFiles;
  watchSubmit();
  // Many application forms render late (React); look again for a few seconds.
  show(false);
  let n = 0;
  const t = setInterval(() => { if (root || ++n > 10) clearInterval(t); else show(false); }, 1000);
})();
