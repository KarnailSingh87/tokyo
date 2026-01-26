import { optionalEnv, providerKey } from "../core/env.js";

export interface TranscriptResult {
  ok: boolean;
  text: string;
  provider: string;
  reason?: string;
}

export interface Transcriber {
  readonly name: string;
  transcribe(audio: Buffer, mimeType: string): Promise<TranscriptResult>;
}

export class PlaceholderTranscriber implements Transcriber {
  readonly name = "placeholder-stt";

  async transcribe(audio: Buffer, mimeType: string): Promise<TranscriptResult> {
    const secondsEstimate = Math.max(1, Math.round(audio.length / 16_000));
    return {
      ok: true,
      text: `(stt placeholder · ~${secondsEstimate}s of ${mimeType} captured)`,
      provider: this.name,
    };
  }
}

export class WhisperTranscriber implements Transcriber {
  readonly name = "openai-whisper";

  constructor(
    private readonly apiKey: string,
    private readonly baseUrl = optionalEnv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    private readonly model = optionalEnv("TOKYOX_STT_MODEL", "whisper-1")
  ) {}

  async transcribe(audio: Buffer, mimeType: string): Promise<TranscriptResult> {
    const ext = mimeType.includes("webm")
      ? "webm"
      : mimeType.includes("ogg")
        ? "ogg"
        : mimeType.includes("mp4")
          ? "mp4"
          : "wav";
    try {
      const form = new FormData();
      form.append("file", new Blob([new Uint8Array(audio)], { type: mimeType }), `audio.${ext}`);
      form.append("model", this.model);
      const res = await fetch(`${this.baseUrl}/audio/transcriptions`, {
        method: "POST",
        headers: { authorization: `Bearer ${this.apiKey}` },
        body: form,
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) {
        return {
          ok: false,
          text: "",
          provider: this.name,
          reason: `HTTP ${res.status}`,
        };
      }
      const data = (await res.json()) as { text?: string };
      return { ok: true, text: data.text ?? "", provider: this.name };
    } catch (err) {
      return {
        ok: false,
        text: "",
        provider: this.name,
        reason: err instanceof Error ? err.message : String(err),
      };
    }
  }
}

export function createTranscriber(): Transcriber {
  const key = providerKey("openai");
  if (key) return new WhisperTranscriber(key);
  return new PlaceholderTranscriber();
}
