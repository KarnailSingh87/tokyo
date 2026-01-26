const $ = (id) => document.getElementById(id);

let ws: WebSocket | null = null;
let paired = false;

function connect(token: string) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/phone`);
  ws.onopen = () => {
    ws?.send(JSON.stringify({ type: "hello", token }));
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "welcome") {
      paired = true;
      localStorage.setItem("tokyox_pair_token", token);
      showView("approvals-view");
      renderApprovals(msg.approvals ?? []);
    } else if (msg.type === "pending") {
      renderApprovals(msg.approvals ?? []);
    } else if (msg.type === "approval_request") {
      addApproval(msg);
    } else if (msg.type === "approval_update") {
      removeApproval(msg.id);
    }
  };
  ws.onclose = () => {
    if (paired) setTimeout(() => connect(token), 3000);
  };
  ws.onerror = () => ws?.close();
}

function showView(id: string) {
  $$("view").forEach((v) => v.hidden = true);
  $(id).hidden = false;
}

function $$(sel: string) {
  return Array.from(document.querySelectorAll(sel));
}

function renderApprovals(list: any[]) {
  const el = $("approvals-list");
  el.innerHTML = "";
  if (list.length === 0) {
    $("empty-msg").hidden = false;
    $("pending-count").textContent = "0";
    return;
  }
  $("empty-msg").hidden = true;
  $("pending-count").textContent = String(list.length);
  for (const a of list) addApproval(a);
}

function addApproval(a: any) {
  const el = document.createElement("div");
  el.className = "approval";
  el.dataset.id = a.id;
  el.innerHTML = `
    <div class="approval-head">
      <span class="approval-tool">${escapeHtml(a.tool)}</span>
      <span class="tier tier-${a.tier}">TIER ${a.tier}</span>
    </div>
    <div class="approval-args">${escapeHtml(JSON.stringify(a.args ?? {}))}</div>
    <div class="approval-actions">
      <button class="btn ok" data-action="approve">APPROVE</button>
      <button class="btn no" data-action="deny">DENY</button>
    </div>`;
  el.querySelector(".ok")?.addEventListener("click", () => sendDecision(a.id, true));
  el.querySelector(".no")?.addEventListener("click", () => sendDecision(a.id, false));
  $("approvals-list").prepend(el);
}

function removeApproval(id: string) {
  const el = document.querySelector(`.approval[data-id="${id}"]`);
  el?.remove();
  const count = document.querySelectorAll(".approval").length;
  $("pending-count").textContent = String(count);
  if (count === 0) $("empty-msg").hidden = false;
}

function sendDecision(id: string, approved: boolean) {
  ws?.send(JSON.stringify({ type: "decision", id, approved }));
  const el = document.querySelector(`.approval[data-id="${id}"]`);
  if (el) el.style.opacity = "0.5";
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, c => ({'&':'&','<':'<','>':'>','"':'"',"'":'''}[c]));
}

$("pair-btn").addEventListener("click", () => {
  const t = $("pair-input").value.trim().replace(/-/g, "");
  if (t.length === 16) connect(t);
});

$("pair-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("pair-btn").click();
});

const saved = localStorage.getItem("tokyox_pair_token");
if (saved) connect(saved);
else showView("pair-view");

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}