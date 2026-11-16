// Talks to the job-alerts helper (python -m jobalerts bot) on 127.0.0.1. Content scripts send messages here because
// a page's own origin cannot read the helper (it sends no CORS headers on purpose).

async function settings() {
  const s = await chrome.storage.local.get({ port: 8765, token: "" });
  return { base: `http://127.0.0.1:${s.port}`, token: s.token };
}

async function api(method, path, body) {
  const { base, token } = await settings();
  if (!token) return { error: "no-token" };
  const r = await fetch(base + path, {
    method,
    headers: { "X-Job-Alerts-Token": token, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) return { error: "bad-token" };
  return r.json();
}

async function file(path) {
  const { base, token } = await settings();
  const r = await fetch(base + path, { headers: { "X-Job-Alerts-Token": token } });
  if (!r.ok) return { error: `HTTP ${r.status}` };
  const buf = new Uint8Array(await r.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return { name: r.headers.get("X-File-Name") || "document.pdf", type: r.headers.get("Content-Type") || "application/pdf",
           base64: btoa(bin) };
}

// Company career pages (stripe.com, …) embed the ATS form in an iframe, so the panel and the form are often in
// different frames. The copy of content.js already running in the form's frame answers "fill-here"; frames without
// a form stay silent. If no frame answers, inject into every frame we may enter (one at a time, so a frame we are
// not allowed into, like a chat widget, does not sink the rest) and fill there.
async function fillAll(tabId, profile, info) {
  try {
    const r = await chrome.tabs.sendMessage(tabId, { type: "fill-here", profile, info });
    if (r) return r;
  } catch (_) { /* no frame with a form answered */ }
  const total = { filled: 0, left: 0, notes: [], frames: 0 };
  const frames = await chrome.webNavigation.getAllFrames({ tabId }).catch(() => [{ frameId: 0 }]);
  for (const { frameId } of frames) {
    const target = { tabId, frameIds: [frameId] };
    try {
      await chrome.scripting.executeScript({ target, files: ["content.js"] });
      const [res] = await chrome.scripting.executeScript({
        target, args: [profile, info],
        func: (p, i) => window.__jobAlertsFillHere ? window.__jobAlertsFillHere(p, i) : null,
      });
      const r = res && res.result;
      if (r) { total.filled += r.filled; total.left += r.left; total.notes.push(...r.notes); total.frames++; }
    } catch (_) { /* not allowed into this frame */ }
  }
  return total;
}

// An ATS iframe found a form: put the panel on the outer page, where it is visible. Fails without access to the
// outer site (only granted by clicking the toolbar button); the iframe then shows the panel itself.
async function showTop(tabId) {
  const target = { tabId, frameIds: [0] };
  await chrome.scripting.executeScript({ target, files: ["content.js"] });
  await chrome.scripting.executeScript({ target, func: () => window.__jobAlertsShow && window.__jobAlertsShow(true) });
  return { ok: true };
}

// "Answer the rest with Claude": the frame with the form collects its open questions and fills the answers.
async function aiAll(tabId, info) {
  const r = await chrome.tabs.sendMessage(tabId, { type: "ai-here", info });
  if (!r) throw new Error("no frame with a form");
  return r;
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const tabId = sender.tab && sender.tab.id;
  // A frame's progress line goes to the panel on the outer page.
  const run = msg.type === "stop-all" ? chrome.tabs.sendMessage(tabId, { type: "stop" }).catch(() => {}).then(() => ({ ok: true }))
    : msg.type === "progress" ? chrome.tabs.sendMessage(tabId, msg, { frameId: 0 }).catch(() => {}).then(() => ({ ok: true }))
    : msg.type === "fill-all" ? fillAll(tabId, msg.profile, msg.info)
    : msg.type === "ai-all" ? aiAll(tabId, msg.info)
    : msg.type === "show-top" ? showTop(tabId)
    : msg.type === "file" ? file(msg.path) : api(msg.method || "GET", msg.path, msg.body);
  run.then(reply, (e) => reply({ error: ["fill-all", "show-top", "ai-all"].includes(msg.type) ? "frames" : "helper-offline",
                                 detail: String(e) }));
  return true; // async reply
});

// Toolbar button: show the panel on any page (company career sites that embed a form, unknown ATSs).
chrome.action.onClicked.addListener(async (tab) => {
  await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ["content.js"] });
  await chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: true },
    func: () => window.__jobAlertsShow && window.__jobAlertsShow(true),
  });
});
