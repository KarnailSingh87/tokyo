from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class VoicePreset:
    id: str
    name: str
    description: str
    stability: float
    similarity_boost: float
    style: float


@dataclass
class VoiceConfig:
    version: str
    default_preset: str
    voice_id_env: str
    presets: list[VoicePreset]


def load_voices(path: str) -> VoiceConfig:
    import json
    with open(path) as f:
        raw = json.load(f)
    return VoiceConfig(
        version=raw.get("version", "0.1.0"),
        default_preset=raw.get("defaultPreset", "nova"),
        voice_id_env=raw.get("voiceIdEnv", "ELEVENLABS_VOICE_ID"),
        presets=[VoicePreset(**p) for p in raw.get("presets", [])],
    )


@dataclass
class SynthesisResult:
    ok: bool
    audio: bytes | None
    preset: str
    provider: str
    reason: str | None = None
    latency_ms: int = 0


class ElevenLabsTTS:
    def __init__(self, config: VoiceConfig):
        self._config = config
        self._base_url = os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")

    def presets(self) -> list[VoicePreset]:
        return self._config.presets

    def default_preset(self) -> VoicePreset:
        return next((p for p in self._config.presets if p.id == self._config.default_preset), self._config.presets[0])

    def resolve_preset(self, preset_id: str | None) -> VoicePreset:
        if not preset_id:
            return self.default_preset()
        return next((p for p in self._config.presets if p.id == preset_id.lower()), self.default_preset())

    def is_configured(self) -> bool:
        return bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get(self._config.voice_id_env))

    def _voice_id_for(self, preset: VoicePreset) -> str:
        return os.environ.get(f"ELEVENLABS_VOICE_{preset.id.upper()}") or os.environ.get(self._config.voice_id_env, "")

    async def synthesize(self, text: str, preset_id: str | None = None) -> SynthesisResult:
        started = time.time()
        preset = self.resolve_preset(preset_id)
        key = os.environ.get("ELEVENLABS_API_KEY")
        voice_id = self._voice_id_for(preset)

        if not key or not voice_id:
            return SynthesisResult(
                ok=False,
                audio=None,
                preset=preset.id,
                provider="elevenlabs",
                reason="safe fallback: missing ELEVENLABS_API_KEY or voice id",
                latency_ms=0,
            )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{self._base_url}/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text[:4000],
                        "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5"),
                        "voice_settings": {
                            "stability": preset.stability,
                            "similarity_boost": preset.similarity_boost,
                            "style": preset.style,
                            "use_speaker_boost": True,
                        },
                    },
                )
                if not resp.is_success:
                    return SynthesisResult(
                        ok=False,
                        audio=None,
                        preset=preset.id,
                        provider="elevenlabs",
                        reason=f"safe fallback: elevenlabs HTTP {resp.status_code}",
                        latency_ms=int((time.time() - started) * 1000),
                    )
                audio = resp.content
                return SynthesisResult(
                    ok=True,
                    audio=audio,
                    preset=preset.id,
                    provider="elevenlabs",
                    latency_ms=int((time.time() - started) * 1000),
                )
        except Exception as err:
            return SynthesisResult(
                ok=False,
                audio=None,
                preset=preset.id,
                provider="elevenlabs",
                reason=f"safe fallback: {err}",
                latency_ms=int((time.time() - started) * 1000),
            )