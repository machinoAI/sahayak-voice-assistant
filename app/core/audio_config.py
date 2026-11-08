"""
Audio Configuration & Transport Constants for Sahayak Voice Assistant.
"""

from dataclasses import dataclass

@dataclass(frozen=True)
class AudioConfig:
    SAMPLE_RATE: int = 16000          # 16 kHz
    CHANNELS: int = 1                 # Mono
    BYTES_PER_SAMPLE: int = 2         # 16-bit linear PCM (2 bytes)
    FRAME_DURATION_MS: int = 20       # 20ms frame duration
    
    @property
    def SAMPLES_PER_FRAME(self) -> int:
        return (self.SAMPLE_RATE * self.FRAME_DURATION_MS) // 1000  # 320 samples
        
    @property
    def CHUNK_SIZE_BYTES(self) -> int:
        return self.SAMPLES_PER_FRAME * self.BYTES_PER_SAMPLE       # 640 bytes

AUDIO_CONFIG = AudioConfig()
