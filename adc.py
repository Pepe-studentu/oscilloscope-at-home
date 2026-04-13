import time
import numpy as np


class ADC:
    """Wraps a serial connection and holds device-specific constants."""

    def __init__(self, serial_connection, voltage_range=5.0, chunk_size=256):
        self.serial = serial_connection
        self.voltage_range = voltage_range  # full-scale voltage (e.g. 5.0 V)
        self.chunk_size = chunk_size        # samples per read() call
        # TODO: linearize — callable or LUT for non-linear ADCs (e.g. ESP32 internal ADC)

    @property
    def sample_rate(self) -> int:
        """Samples per second (baudrate is used as a convention for sample rate)."""
        return self.serial.baudrate

    def read(self, n: int) -> bytes:
        return self.serial.read(n)


def _make_waveform(n=2026):
    t = np.linspace(0, 4 * np.pi, n)
    wave = 80 + 50 * np.sin(2 * t) + 30 * np.sin(3*t)
    return np.clip(wave, 0, 255).astype(np.uint8)


class FakeSerial:
    """Simulates an ADC over serial for use without hardware."""
    _DATA = _make_waveform()
    DELAY = 0.0001
    baudrate = round(1 / DELAY)

    def __init__(self):
        self._idx = 0

    def read(self, n):
        chunk = [int(self._DATA[(self._idx + i) % len(self._DATA)]) for i in range(n)]
        self._idx = (self._idx + n) % len(self._DATA)
        time.sleep(self.DELAY * n)
        return bytes(chunk)