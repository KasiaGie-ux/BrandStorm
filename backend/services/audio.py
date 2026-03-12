"""Audio chunk buffering and format helpers.

For hackathon MVP: minimal buffering. The Live API handles audio
encoding/decoding natively — this module buffers incoming client
audio chunks before forwarding to the Live API session.
"""

import logging
from collections import deque

logger = logging.getLogger("brand-agent")

# Live API expects PCM 16-bit 16kHz mono
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


class AudioBuffer:
    """Buffers audio chunks from the client before sending to Live API."""

    def __init__(self, session_id: str, max_chunks: int = 100) -> None:
        self.session_id = session_id
        self._chunks: deque[bytes] = deque(maxlen=max_chunks)
        self._total_bytes = 0

    def add_chunk(self, chunk: bytes) -> None:
        """Add an audio chunk to the buffer."""
        self._chunks.append(chunk)
        self._total_bytes += len(chunk)

    def drain(self) -> bytes:
        """Drain all buffered chunks into a single bytes object."""
        if not self._chunks:
            return b""
        combined = b"".join(self._chunks)
        self._chunks.clear()
        return combined

    def has_data(self) -> bool:
        return len(self._chunks) > 0

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes
