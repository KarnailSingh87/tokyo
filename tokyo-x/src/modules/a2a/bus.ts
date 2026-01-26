export interface A2AMessage {
  from: string;
  topic: string;
  body: unknown;
  ts: string;
}

type Handler = (msg: A2AMessage) => void;

export class AgentBus {
  private subs = new Map<string, Set<Handler>>();
  private history: A2AMessage[] = [];

  publish(from: string, topic: string, body: unknown): number {
    const msg: A2AMessage = { from, topic, body, ts: new Date().toISOString() };
    this.history.push(msg);
    if (this.history.length > 200) this.history.shift();
    const listeners = this.subs.get(topic);
    if (!listeners) return 0;
    let delivered = 0;
    for (const h of listeners) {
      try {
        h(msg);
        delivered += 1;
      } catch {
        continue;
      }
    }
    return delivered;
  }

  subscribe(topic: string, handler: Handler): () => void {
    if (!this.subs.has(topic)) this.subs.set(topic, new Set());
    this.subs.get(topic)?.add(handler);
    return () => this.subs.get(topic)?.delete(handler);
  }

  topics(): string[] {
    return [...this.subs.keys()];
  }

  getHistory(n = 20): A2AMessage[] {
    return this.history.slice(-n);
  }
}
