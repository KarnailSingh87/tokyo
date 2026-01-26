const $ = (id) => document.getElementById(id);

const ORG_MOCK = {
  ceo: { name: "Kapil", role: "CEO" },
  orchestrator: { id: "tokyo-x", role: "Orchestrator" },
  managers: [
    { name: "Research Manager", domain: "research", workers: [{ name: "Web Researcher" }, { name: "Doc Reader" }, { name: "Summarizer" }] },
    { name: "Code Manager", domain: "engineering", workers: [{ name: "Coder" }, { name: "Reviewer" }, { name: "Tester" }] },
    { name: "PC Ops Manager", domain: "local-machine", workers: [{ name: "File Worker" }, { name: "Terminal Worker" }, { name: "Browser Worker" }, { name: "Screen Worker" }] },
    { name: "Comms Manager", domain: "communication", workers: [{ name: "Voice Worker" }, { name: "Notifier" }] },
    { name: "Memory & Cost Manager", domain: "memory-accounting", workers: [{ name: "Memory Curator" }, { name: "Cost Tracker" }] },
  ],
};

const TAG_CLASS = {
  research: "tag-violet",
  engineering: "tag-blue",
  "local-machine": "tag-amber",
  communication: "tag-pink",
  "memory-accounting": "tag-teal",
};

const TASK_POOL = [
  { name: "Index workspace docs", mgr: "memory-accounting" },
  { name: "Summarize inbox thread", mgr: "communication" },
  { name: "Run unit test suite", mgr: "engineering" },
  { name: "Fetch market brief", mgr: "research" },
  { name: "Backup workspace", mgr: "local-machine" },
  { name: "Draft spec outline", mgr: "engineering" },
  { name: "Screen triage sweep", mgr: "local-machine" },
  { name: "Curate daily memory", mgr: "memory-accounting" },
  { name: "Compile competitor scan", mgr: "research" },
];

const APPROVAL_TEMPLATES = [
  { tool: "terminal.exec", tier: 2, args: "npm test --workspace" },
  { tool: "fs.write", tier: 1, args: "reports/weekly.md" },
  { tool: "screen.capture", tier: 2, args: "display 1" },
  { tool: "browser.open", tier: 1, args: "https://news.ycombinator.com" },
  { tool: "notify.send", tier: 1, args: "slack #ops ping" },
  { tool: "fs.delete", tier: 2, args: "tmp/old-build/" },
];

const REPLIES = [
  "Directive received. Routing to PC Ops Manager with a Tier-2 gate on shell access.",
  "Acknowledged, Kapil. Research Manager is spinning up a worker swarm.",
  "Plan drafted: 3 steps, 1 confirmation needed before terminal execution.",
  "Memory Curator logged this directive to the digital twin. Executing now.",
  "Understood. I will pause for your approval the moment risk tier exceeds 1.",
];

let lastTokyoText = "";

const state = {
  orb: "idle",
  listening: false,
  tasks: [],
  approvals: [],
  realApprovals: [],
  cost: { total: 0.0842, openai: 0.0521, openrouter: 0.0227, elevenlabs: 0.0094 },
  templateIdx: 0,
  taskId: 0,
  realMode: false,
};

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&", "<": "<", ">": ">", '"': """, "'": "'" }[c]));

function toast(text, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

function audit(text) {
  $("audit-line").textContent = `[audit] ${new Date().toLocaleTimeString()} · ${text}`;
}

function setOrb(next) {
  state.orb = next;
  const orb = $("orb");
  orb.className = `orb state-${next}`;
  $("orb-state").textContent = next.toUpperCase();
  $("eq").className = next === "speaking" ? "eq on" : "eq";
}

function pushMsg(role, text) {
  const feed = $("feed");
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
  if (role === "tokyo") lastTokyoText = text;
}

function tickClock() {
  $("clock").textContent = new Date().toLocaleTimeString("en-GB");
}

function seedStats(key, min, max) {
  let v = min + Math.random() * (max - min);
  return () => {
    v = Math.min(max, Math.max(min, v + (Math.random() * 14 - 7)));
    const pct = Math.round(v);
    $(`g-${key}`).style.width = `${pct}%`;
    $(`v-${key}`).textContent = `${pct}%`;
  };
}

function renderOrg(org) {
  const tree = $("org-tree");
  tree.innerHTML = "";
  const root = document.createElement("div");
  root.className = "node root";
  root.textContent = `${org.ceo.name.toUpperCase()} · ${org.ceo.role.toUpperCase()}`;
  const orch = document.createElement("div");
  orch.className = "node orch";
  orch.textContent = `${org.orchestrator.id.toUpperCase()} · ${org.orchestrator.role.toUpperCase()}`;
  const list = document.createElement("ul");
  for (const mgr of org.managers) {
    const li = document.createElement("li");
    li.dataset.domain = mgr.domain;
    const m = document.createElement("div");
    m.className = "node mgr";
    m.textContent = mgr.name;
    li.appendChild(m);
    const chips = document.createElement("div");
    chips.className = "chips";
    for (const w of mgr.workers) {
      const c = document.createElement("span");
      c.textContent = w.name;
      chips.appendChild(c);
    }
    li.appendChild(chips);
    list.appendChild(li);
  }
  tree.append(root, orch, list);
}

function spawnTask() {
  const t = TASK_POOL[Math.floor(Math.random() * TASK_POOL.length)];
  state.taskId += 1;
  state.tasks.push({ id: state.taskId, name: t.name, mgr: t.mgr, progress: 0, status: "queued" });
}

function renderTasks() {
  const wrap = $("tasks");
  wrap.innerHTML = "";
  for (const t of state.tasks) {
    const el = document.createElement("div");
    el.className = `task${t.status === "done" ? " done" : ""}`;
    el.innerHTML = `
      <div class="task-top">
        <span class="task-name">${esc(t.name)}</span>
        <span class="tag ${TAG_CLASS[t.mgr] ?? "tag-blue"}">${esc(t.mgr)}</span>
      </div>
      <div class="task-track"><div class="task-fill" style="width:${t.progress}%"></div></div>`;
    wrap.appendChild(el);
  }
}

function tickTasks() {
  for (const t of state.tasks) {
    if (t.status === "queued" && Math.random() < 0.4) t.status = "running";
    if (t.status === "running") {
      t.progress = Math.min(100, t.progress + 2 + Math.random() * 9);
      if (t.progress >= 100) {
        t.status = "done";
        audit(`task complete · "${t.name}" verified by orchestrator`);
      }
    }
  }
  const done = state.tasks.filter((t) => t.status === "done");
  for (const t of done) setTimeout(() => {
    state.tasks = state.tasks.filter((x) => x.id !== t.id);
    renderTasks();
  }, 2400);
  if (state.tasks.length < 4 && Math.random() < 0.7) spawnTask();
  while (state.tasks.length > 6) state.tasks.shift();
  renderTasks();
}

function renderApprovals() {
  const wrap = $("approvals");
  wrap.innerHTML = "";
  const all = state.realMode && state.realApprovals.length > 0 ? state.realApprovals : state.approvals;
  const count = $("approval-count");
  count.textContent = all.length;
  count.classList.toggle("zero", all.length === 0);
  if (all.length === 0) {
    wrap.innerHTML = '<p class="muted note">inbox clear</p>';
    return;
  }
  for (const a of all) {
    const el = document.createElement("div");
    el.className = "approval";
    const isReal = state.realMode && state.realApprovals.some((ra) => ra.id === a.id);
    const showToken = a.token && isReal;
    el.innerHTML = `
      <div class="approval-top">
        <span class="approval-tool">${esc(a.tool)}</span>
        <span class="tier tier-${a.tier}">TIER ${a.tier}</span>
      </div>
      <div class="approval-args">${esc(JSON.stringify(a.args ?? {}))}</div>
      <div class="approval-actions">
        <button class="btn btn-approve" type="button" data-action="approve">APPROVE</button>
        <button class="btn btn-deny" type="button" data-action="deny">DENY</button>
        ${showToken ? `<span class="mono muted" style="font-size:9px;margin-left:8px">token: ${esc(a.token.slice(0,16))}…</span>` : ""}
      </div>`;
    const [ok, no] = el.querySelectorAll("button");
    ok.addEventListener("click", () => resolveApproval(a.id, true, isReal, a.token));
    no.addEventListener("click", () => resolveApproval(a.id, false, isReal, a.token));
    wrap.appendChild(el);
  }
}

async function resolveApproval(id: string, approved: boolean, isReal: boolean, token?: string) {
  if (isReal) {
    try {
      const res = await fetch("/api/approvals/resolve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id, approved, token: token ?? "" }),
      });
      if (!res.ok) throw new Error("resolve failed");
      toast(`${approved ? "Approved" : "Denied"}: via server`, approved ? "ok" : "warn");
      audit(`approval ${approved ? "granted" : "denied"} by kapil (server) · id ${id}`);
      await loadRealApprovals();
    } catch (err) {
      toast(`Server resolve failed: ${err}`, "warn");
    }
    return;
  }
  const a = state.approvals.find((x) => x.id === id);
  if (!a) return;
  state.approvals = state.approvals.filter((x) => x.id !== id);
  renderApprovals();
  toast(`${approved ? "Approved" : "Denied"}: ${a.tool}`, approved ? "ok" : "warn");
  audit(`approval ${approved ? "granted" : "denied"} by kapil (local) · ${a.tool}`);
  pushMsg("system", approved ? `approval granted → ${a.tool}` : `approval denied → ${a.tool}`);
}

function spawnApproval() {
  if (state.approvals.length >= 3) return;
  const t = APPROVAL_TEMPLATES[state.templateIdx % APPROVAL_TEMPLATES.length];
  state.templateIdx += 1;
  state.approvals.push({ id: `ap_${Date.now()}`, tool: t.tool, tier: t.tier, args: t.args });
  renderApprovals();
  toast(`Approval requested: ${t.tool}`, "warn");
  audit(`permission gate · CONFIRM raised for ${t.tool} (tier ${t.tier})`);
}

async function loadRealApprovals() {
  try {
    const res = await fetch("/api/approvals");
    const list = await res.json();
    state.realApprovals = list;
    state.realMode = list.length > 0;
    renderApprovals();
  } catch {
    state.realApprovals = [];
    state.realMode = false;
    renderApprovals();
  }
}

function tickCost() {
  const delta = 0.0004 + Math.random() * 0.0021;
  state.cost.total += delta;
  state.cost.openai += delta * 0.62;
  state.cost.openrouter += delta * 0.27;
  state.cost.elevenlabs += delta * 0.11;
  $("cost-total").textContent = `$${state.cost.total.toFixed(4)}`;
  $("cost-openai").textContent = `$${state.cost.openai.toFixed(4)}`;
  $("cost-openrouter").textContent = `$${state.cost.openrouter.toFixed(4)}`;
  $("cost-elevenlabs").textContent = `$${state.cost.elevenlabs.toFixed(4)}`;
}

async function handleDirective(text, viaVoice = false) {
  pushMsg("user", viaVoice ? `(voice) ${text}` : text);
  setOrb("processing");
  audit(`goal received · routing via orchestrator`);
  setTimeout(() => {
    const reply = REPLIES[Math.floor(Math.random() * REPLIES.length)];
    pushMsg("tokyo", reply);
    setOrb("speaking");
    setTimeout(() => setOrb(state.listening ? "listening" : "idle"), 1600);
    if (Math.random() < 0.45) setTimeout(spawnApproval, 900);
  }, 900 + Math.random() * 600);
}

async function speakLast() {
  if (!lastTokyoText) { toast("no tokyo message to speak", "warn"); return; }
  const preset = $("voice-preset").value.toLowerCase();
  try {
    const res = await fetch("/api/voice/tts", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: lastTokyoText, preset }),
    });
    if (!res.ok) {
      const j = await res.json();
      toast(`TTS fallback: ${j.reason ?? "unavailable"}`, "warn");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play();
    setOrb("speaking");
    audio.onended = () => { URL.revokeObjectURL(url); setOrb(state.listening ? "listening" : "idle"); };
  } catch (err) {
    toast(`TTS error: ${err}`, "warn");
  }
}

function bindConsole() {
  $("cmd-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("cmd-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    handleDirective(text);
  });
}

function bindMic() {
  const btn = $("mic-btn");
  btn.addEventListener("click", async () => {
    if (state.listening) {
      stopListening();
      return;
    }
    state.listening = true;
    btn.classList.add("active");
    btn.textContent = "LISTENING…";
    $("wave").classList.add("active");
    setOrb("listening");
    audit("voice link open · attempting real mic capture");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        const arrayBuffer = await blob.arrayBuffer();
        const res = await fetch("/api/voice/stt", {
          method: "POST",
          headers: { "content-type": "audio/webm" },
          body: arrayBuffer,
        });
        const result = await res.json();
        if (result.ok && result.text) {
          handleDirective(result.text, true);
        } else {
          toast("STT unavailable, using simulation", "warn");
          handleDirective("status report, TOKYO", true);
        }
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      setTimeout(() => { if (state.listening) { recorder.stop(); stopListening(); } }, 4000);
    } catch (err) {
      audit(`mic capture failed: ${err} · falling back to simulation`);
      toast("mic permission denied · simulation mode", "warn");
      setTimeout(() => { if (state.listening) { stopListening(); handleDirective("status report, TOKYO", true); } }, 800);
    }
  });

  function stopListening() {
    state.listening = false;
    btn.classList.remove("active");
    btn.textContent = "ENGAGE MIC";
    $("wave").classList.remove("active");
    setOrb("idle");
  }
}

function bindSpeak() {
  $("speak-btn").addEventListener("click", speakLast);
}

function bindToggles() {
  $("tg-proactive").addEventListener("click", (e) => {
    const btn = e.currentTarget;
    btn.classList.toggle("on");
    const on = btn.classList.contains("on");
    btn.querySelector("b").textContent = on ? "ON" : "OFF";
    toast(`Proactive mode ${on ? "enabled" : "disabled"}`, on ? "ok" : "warn");
    audit(`proactive mode → ${on ? "on" : "off"}`);
  });
  $("tg-sim").addEventListener("click", (e) => {
    const btn = e.currentTarget;
    btn.classList.toggle("on");
    const on = btn.classList.contains("on");
    btn.querySelector("b").textContent = on ? "ON" : "OFF";
    toast(`Simulation mode ${on ? "enabled" : "disabled"}`, on ? "ok" : "warn");
    audit(`simulation mode → ${on ? "on" : "off"}`);
  });
}

async function loadPairing() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.pairingCode) {
      $("pair-code").textContent = `PAIR ${data.pairingCode}`;
    }
  } catch {}
}

async function boot() {
  tickClock();
  setInterval(tickClock, 1000);

  const cpu = seedStats("cpu", 14, 88);
  const mem = seedStats("mem", 38, 84);
  const net = seedStats("net", 6, 92);
  cpu(); mem(); net();
  setInterval(() => { cpu(); mem(); net(); }, 1600);

  try {
    const res = await fetch("/api/org");
    renderOrg(res.ok ? await res.json() : ORG_MOCK);
  } catch {
    renderOrg(ORG_MOCK);
  }

  for (let i = 0; i < 3; i++) spawnTask();
  state.tasks.forEach((t) => { t.status = "running"; t.progress = 10 + Math.random() * 40; });
  renderTasks();
  setInterval(tickTasks, 900);

  renderApprovals();
  setInterval(spawnApproval, 11000);
  setInterval(loadRealApprovals, 4000);

  tickCost();
  setInterval(tickCost, 1500);

  pushMsg("system", "TOKYO-X core online · phase 8 dashboard · real endpoints active");
  pushMsg("tokyo", "Good day, Kapil. All five managers report ready. Awaiting your directive.");
  audit("boot sequence complete · 5 managers · 14 workers registered");

  await loadPairing();
  bindConsole();
  bindMic();
  bindSpeak();
  bindToggles();
  setOrb("idle");
}

boot();