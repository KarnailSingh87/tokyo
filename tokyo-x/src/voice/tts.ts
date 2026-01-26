import { readFileSync } from "node:fs";
import { optionalEnv, providerKey } from "../core/env.js";

export interface VoicePreset {
  id: string;
  name: string;
  description: string;
  stability: number;
  similarityBoost: number;
  style: number;
}

export interface VoiceConfig {
  version: string;
  defaultPreset: string;
  voiceIdEnv: string;
  presets: VoicePreset[];
}

export function loadVoices(path: string): VoiceConfig {
  const cfg = JSON.parse(readFileSync(path, "utf8")) as VoiceConfig;
  if (!Array.isArray(cfg.presets) || cfg.presets.length === 0) {
    throw new Error("invalid voices config: no presets");
  }
  return cfg;
}

export interface SynthesisResult {
  ok: boolean;
  audio: Buffer | null;
  preset: string;
  provider: string;
  reason?: string;
  latencyMs: number;
}

export class ElevenLabsTTS {
  constructor(private readonly config: VoiceConfig) {}

  presets(): VoicePreset[] {
    return this.config.presets;
  }

  defaultPreset(): VoicePreset {
    return (
      this.config.presets.find((p) => p.id === this.config.defaultPreset) ?? this.config.presets[0]
    );
  }

  resolvePreset(id?: string): VoicePreset {
    if (!id) return this.defaultPreset();
    return this.config.presets.find((p) => p.id === id.toLowerCase()) ?? this.defaultPreset();
  }

  isConfigured(): boolean {
    return !!providerKey("elevenlabs") && !!optionalEnv(this.config.voiceIdEnv);
  }

  private voiceIdFor(preset: VoicePreset): string {
    return (
      optionalEnv(`ELEVENLABS_VOICE_${preset.id.toUpperCase()}`) ||
      optionalEnv(this.config.voiceIdEnv)
    );
  }

  async synthesize(text: string, presetId?: string): Promise<SynthesisResult> {
    const started = Date.now();
    const preset = this.resolvePreset(presetId);
    const key = providerKey("elevenlabs");
    const voiceId = this.voiceIdFor(preset);

    if (!key || !voiceId) {
      return {
        ok: false,
        audio: null,
        preset: preset.id,
        provider: "elevenlabs",
        reason: "safe fallback: missing ELEVENLABS_API_KEY or voice id",
        latencyMs: 0,
      };
    }

    const baseUrl = optionalEnv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1");
    try {
      const res = await fetch(
        `${baseUrl}/text-to-speech/${encodeURIComponent(voiceId)}`,
        {
          method: "POST",
          headers: {
            "xi-api-key": key,
            "content-type": "application/json",
            accept: "audio/mpeg",
          },
          body: JSON.stringify({
            text: text.slice(0, 4000),
            model_id: optionalEnv("ELEVENLABS_MODEL", "eleven_turbo_v2_5"),
            voice_settings: {
              stability: preset.stability,
              similarity_boost: preset.similarityBoost,
              style: preset.style,
              use_speaker_boost: true,
            },
          }),
          signal: AbortSignal.timeout(20_000),
        }
      );
      if (!res.ok) {
        return {
          ok: false,
          audio: null,
          preset: preset.id,
          provider: "elevenlabs",
          reason: `safe fallback: elevenlabs HTTP ${res.status}`,
          latencyMs: Date.now() - started,
        };
      }
      const audio = Buffer.from(await res.arrayBuffer());
      return {
        ok: true,
        audio,
        preset: preset.id,
        provider: "elevenlabs",
        latencyMs: Date.now() - started,
      };
    } catch (err) {
      return {
        ok: false,
        audio: null,
        preset: preset.id,
        provider: "elevenlabs",
        reason: `safe fallback: ${err instanceof Error ? err.message : String(err)}`,
        latencyMs: Date.now() - started,
      };
    }
  }
}
