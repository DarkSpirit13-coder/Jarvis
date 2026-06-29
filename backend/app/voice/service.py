"""Voice service contracts for speech recognition and synthesis."""

from abc import ABC, abstractmethod

from app.core.errors import IntegrationNotConfiguredError


class VoiceService(ABC):
    """Interface for speech-to-text and text-to-speech providers."""

    @abstractmethod
    async def transcribe(self, audio: bytes, content_type: str) -> str:
        """Transcribe audio bytes into text."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech audio from text."""


class DisabledVoiceService(VoiceService):
    """Voice service used before a speech provider is configured."""

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        """Fail explicitly because voice transcription is unavailable."""
        raise IntegrationNotConfiguredError("Voice transcription provider is not configured")

    async def synthesize(self, text: str) -> bytes:
        """Fail explicitly because voice synthesis is unavailable."""
        raise IntegrationNotConfiguredError("Voice synthesis provider is not configured")
