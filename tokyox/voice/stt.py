from __future__ import annotations
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass
class TranscriptResult:
    ok: bool
    text: str
    provider: str
    reason: str | None = None


class Transcriber(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptResult: ...


class PlaceholderTranscriber(Transcriber):
    name = "placeholder-stt"

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptResult:
        secs = max(1, len(audio) // 16000)
        return TranscriptResult(
            ok=True,
            text=f"(stt placeholder · ~{secs}s of {mime_type} captured)",
            provider=self.name,
        )


class WhisperTranscriber(Transcriber):
    name = "openai-whisper"

    def __init__(self, api_key: str, base_url: str | None = None, model: str | None = None):
        self._api_key = api_key
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._model = model or os.environ.get("TOKYOX_STT_MODEL", "whisper-1")

    async def transcribe(self, audio: bytes, mime_type: str) -> TranscriptResult:
        ext = "webm" if "webm" in mime_type else "ogg" if "ogg" in mime_type else "mp4" if "mp4" in mime_type else "wav"
        try:
            files = {"file": (f"audio.{ext}", audio, mime_type)}
            data = {"model": self._model}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files=files,
                    data=data,
                )
                if not resp.is_success:
                    return TranscriptResult(ok=False, text="", provider=self.name, reason=f"HTTP {resp.status_code}")
                data = resp.json()
                return TranscriptResult(ok=True, text=data.get("text", ""), provider=self.name)
        except Exception as err:
            return TranscriptResult(ok=False, text="", provider=self.name, reason=str(err))


def create_transcriber() -> Transcriber:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return WhisperTranscriber(key)
    return PlaceholderTranscriber()