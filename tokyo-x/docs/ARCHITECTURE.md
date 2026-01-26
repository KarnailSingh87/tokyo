# TOKYO-X Architecture

## Command hierarchy

```
Kapil (CEO)
  └── TOKYO-X (Orchestrator)
        ├── Research Manager
        │     ├── Web Researcher
        │     ├── Doc Reader
        │     └── Summarizer
        ├── Code Manager
        │     ├── Coder / Reviewer / Tester
        ├── PC Ops Manager
        │     ├── File Worker / Terminal Worker / Browser Worker / Screen Worker
        ├── Comms Manager
        │     ├── Voice Worker / Notifier
        └── Memory & Cost Manager
              ├── Memory Curator / Cost Tracker
```

- Kapil issues goals and is the only authority for Tier-2/3 approvals.
- TOKYO-X decomposes goals, delegates to managers, verifies results.
- Managers own a domain and route work to workers; each worker declares the tools it may call and its max risk tier.

## Permission flow (every tool call passes through this gate)

```
Worker calls tool
   → ToolRegistry.validateInput (schema check)
   → PermissionEngine.evaluate
        rules sorted by priority, first match wins
        hard guardrail: destructive terminal commands always DENY
        verdict: ALLOW | CONFIRM | DENY
        CONFIRM + riskTier >= 2 → requires approval token from Kapil
   → AuditSink.record (file audit log + console)
   → execute or request approval
```

## Approval flow (Phase 4+)

```
CONFIRM verdict
   → PendingApprovals.create(decision, args, category, riskTier)
        generates HMAC-signed token (5 min TTL)
        fires onCreate callback → Phone hub broadcasts to paired device
   → Client (desktop/phone) shows approval card
   → User taps APPROVE/DENY
        desktop: POST /api/approvals/resolve {id, approved, token}
        phone: WS message {type:"decision", id, approved} → trusted channel (no token)
   → PendingApprovals.resolve(id, approved, {via, token})
        validates token if needsToken && via!=="phone"
        notifies waiter → AgentLoop continues execution
```

## Voice flow (Phase 3)

```
Desktop mic button → MediaRecorder (webm/opus, ~3s)
   → POST /api/voice/stt (audio buffer)
        Transcriber: OpenAI Whisper if OPENAI_API_KEY, else Placeholder
   → transcript text → handleDirective(text, viaVoice=true)
Tokyo reply → SPEAK button
   → POST /api/voice/tts {text, preset}
        ElevenLabsTTS.synthesize() → audio/mpeg
        fallback if missing key → safe error response
```

## Phone remote (Phase 7)

```
Desktop boot → generates 16-char hex pairing code
Phone opens /phone/ → enter code → WS /ws/phone hello {token}
   → token verified via timing-safe equality
   → Phone receives pending approvals + live broadcast
   → User taps APPROVE/DENY → sends decision WS frame
   → Hub calls PendingApprovals.resolve(id, approved, {via:"phone"})
```

## Risk tiers

| Tier | Meaning | Examples |
| ---- | --------------------------- | ------------------------------------ |
| 0 | Read-only, sandboxed | fs.read, memory.get, voice.stt |
| 1 | Reversible writes in workspace | fs.write, browser.open |
| 2 | System-affecting / spend | terminal.exec, screen.capture |
| 3 | Never allowed without explicit CEO policy change | secrets access, payments, destructive ops |

## Module map

| Path | Phase | Purpose |
| --------------- | ----- | ---------------------------------------------- |
| `src/core` | 0 | Orchestrator, permission engine, tool schema, env, approvals, audit |
| `src/agents` | 0 | Manager/worker registry and specs |
| `src/router` | 2 | Model router with provider abstraction + JSONL logging |
| `src/voice` | 3 | Mic input, STT (Whisper/placeholder), ElevenLabs TTS presets |
| `src/ui` | 1 | Futuristic dashboard UI (orb, panels) + static server |
| `src/tools` | 5 | Safe PC tools: file, terminal, browser, screen with sandbox |
| `src/phone` | 7 | Phone PWA + secure WebSocket approvals |
| `src/modules` | 8 | MCP, A2A, jobs, twin memory, proactive, simulation, skills, costs |
| `config/` | 0 | managers.json, permissions.json, voices.json, models.json, skills.json |
| `logs/audit/` | 4 | Append-only audit trail (JSONL) |
| `logs/twin/` | 8 | Digital twin memory (JSONL) |
| `logs/screens/` | 5 | Screen captures |
| `logs/jobs.jsonl` | 8 | Long-running task events |

## Extension points

- New provider: implement `Provider` interface in `src/router/provider.ts`; register in `createDefaultProviders()`.
- New tool: define `ToolDefinition`, register on orchestrator's `ToolRegistry`; permissions from `config/permissions.json`.
- New manager/worker: add entry to `config/managers.json`; no code changes for routing metadata.
- New skill: add to `config/skills.json`; `SkillRegistry.instantiate()` merges `{{vars}}` into template.
- MCP: run `TOKYOX_MCP_STDIO=1 node dist/modules/mcp/server.js` for stdio JSON-RPC 2.0.
- A2A: `AgentBus.publish(from, topic, body)` for inter-manager messaging.