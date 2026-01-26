# TOKYO-X

Personal AI orchestrator for **Kapil (CEO)**. TOKYO-X acts as the Orchestrator, delegating to domain **Managers** and their **Workers**, with every action gated by a tiered permission engine and an audit trail.

## Design principles

1. **CEO has final authority.** Anything risky requires Kapil's explicit approval.
2. **Schema-first tools.** Every tool declares inputs, category, and risk tier; calls are validated before execution.
3. **Deny by default for danger.** Destructive commands are hard-denied; everything else is allow/confirm per policy.
4. **Everything auditable.** Every permission decision is recorded.

## Quickstart (Phases 0-8 complete)

```bash
cd tokyo-x
cp .env.example .env      # fill in keys for real providers; mock fallback works offline
npm install
npm run typecheck
npm run smoke             # permission engine, tool schema, router, approvals, tools, agent loop
npm run ui                # serves dashboard at http://127.0.0.1:8787 (pairing code printed)
```

## Repository layout

```
tokyo-x/
├── config/
│   ├── managers.json         # org chart: CEO -> Orchestrator -> Managers -> Workers
│   ├── permissions.json      # verdict rules: ALLOW / CONFIRM / DENY by priority
│   ├── voices.json           # ElevenLabs voice presets (Phase 3)
│   ├── models.json           # LLM pricing for cost estimates (Phase 2)
│   └── skills.json           # skill templates (Phase 8)
├── docs/
│   ├── ARCHITECTURE.md       # hierarchy, permission flow, risk tiers, module map
│   └── PHASES.md             # phase tracker (0-8)
├── src/
│   ├── core/                 # orchestrator, permission engine, tool schema, env, approvals, audit
│   ├── agents/               # manager/worker registry
│   ├── router/               # Phase 2: model router (OpenAI + OpenRouter, fallback, JSONL logging)
│   ├── voice/                # Phase 3: STT/TTS pipeline (ElevenLabs TTS, Whisper/placeholder STT)
│   ├── ui/                   # Phase 1: futuristic UI (orb, panels, dashboard) + static server
│   ├── tools/                # Phase 5: safe PC tools (file/terminal/browser/screen with sandbox)
│   ├── phone/                # Phase 7: PWA remote approvals over WebSocket + pairing
│   ├── modules/              # Phase 8: MCP, A2A, jobs, twin memory, proactive, simulation, skills, costs
│   └── dev/smoke.ts          # smoke test for core gates
├── logs/audit/               # append-only decision log (Phase 4)
├── logs/twin/                # digital twin memory JSONL
├── logs/screens/             # screen captures
├── workspace/                # sandbox root for file tools
└── .env.example              # OpenAI / OpenRouter / ElevenLabs / app settings
```

## Permission model at a glance

| Verdict | Meaning |
| -------- | ------------------------------------------------------ |
| `ALLOW` | Auto-approved (read-only / sandboxed actions) |
| `CONFIRM` | Requires Kapil's confirmation; Tier ≥ 2 needs a signed approval token |
| `DENY` | Blocked (destructive commands, secrets access) |

Policy lives in `config/permissions.json`; rules are matched highest-priority-first, with built-in guardrails in code as a backstop. Full details: `docs/ARCHITECTURE.md`.

## Roadmap

See `docs/PHASES.md`. **All 9 phases (0-8) delivered:**
- Phase 0: scaffold, permission engine, tool schema, manager list
- Phase 1: futuristic dashboard UI (animated Tokyo orb, system/agent/voice panels, task queue, approval inbox, cost meter — real org chart via `/api/org`)
- Phase 2: model router with provider abstraction, fallback chains, cost estimation, JSONL logging
- Phase 3: voice pipeline (mic → STT placeholder/Whisper, ElevenLabs TTS presets, safe fallbacks)
- Phase 4: approval tokens (HMAC), pending store, file audit sink, executeTool gate
- Phase 5: safe PC tools (file/terminal/browser/screen) with workspace sandbox guards
- Phase 6: agent execution loop (planning via LLM/heuristic, verification, retry, approval waiting)
- Phase 7: phone PWA remote (secure WebSocket approvals, 16-char pairing code, service worker)
- Phase 8: modules scaffold (MCP stdio server, A2A bus, job queue, twin memory, proactive watcher, simulation mode, skills registry, cost dashboard)