export type ChatRole = "system" | "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
  timeoutMs?: number;
  metadata?: Record<string, string>;
}

export type CompletionRequest = ChatRequest & { model: string };

export interface Usage {
  promptTokens: number;
  completionTokens: number;
}

export interface ChatResponse {
  provider: string;
  model: string;
  content: string;
  usage: Usage;
  finishReason: string;
  latencyMs: number;
  costUsd: number;
}

export interface ModelSpec {
  provider: string;
  model: string;
}
