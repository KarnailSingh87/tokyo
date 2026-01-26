import type { AgentBus } from "../a2a/bus.js";
import type { TwinMemory } from "../memory/twin.js";

export class ProactiveWatcher {
  enabled = false;
  private timer?: ReturnType<typeof setInterval>;
  private lastSuggestions: string[] = [];

  constructor(
    private readonly bus: AgentBus,
    private readonly twin: TwinMemory,
    private readonly intervalMs = 60_000
  ) {}

  start(): void {
    if (this.enabled) return;
    this.enabled = true;
    this.timer = setInterval(() => this.tick(), this.intervalMs);
    this.timer.unref?.();
  }

  stop(): void {
    this.enabled = false;
    if (this.timer) clearInterval(this.timer);
  }

  private tick(): void {
    const recent = this.twin.recent(3);
    const context = recent.length ? recent.map((e) => e.value.slice(0, 120)).join(" | ") : "idle";
    const hour = new Date().getHours();
    const greet = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
    const text = `${greet} scan: ${context}. Suggested next: review inbox, run tests, backup workspace.`;
    this.bus.publish("tokyo-x", "proactive.suggestion", { text });
    this.lastSuggestions.unshift(text);
    if (this.lastSuggestions.length > 10) this.lastSuggestions.pop();
  }

  suggestions(n = 5): string[] {
    return this.lastSuggestions.slice(0, n);
  }
}