const $ = (id) => document.getElementById(id);

chrome.storage.local.get({ port: 8765, token: "" }).then((s) => {
  $("port").value = s.port;
  $("token").value = s.token;
});

$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ port: Number($("port").value) || 8765, token: $("token").value.trim() });
  const r = await chrome.runtime.sendMessage({ type: "api", path: "/api/ping" });
  $("out").textContent = r && r.ok ? "✅ Connected to the job-alerts helper."
    : r && r.error === "bad-token" ? "❌ The helper is running but the token is wrong."
    : "❌ Cannot reach the helper. Is `python -m jobalerts bot` running?";
});
