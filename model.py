"""
The class that holds the data and the logic for the app. It exposes all properties and
doesn't enforce immutability — it's the responsibility of the caller to only touch what
they have to touch.
"""

import numpy as np
import threading
import time

from adc import ADC

# constants:
H_SCALE_MIN = 0.1  # minimum samples-per-pixel (maximum zoom in)
H_SCALE_MAX = 3  # maximum samples-per-pixel (maximum zoom out)
SAFETY_MARGIN = 2000  # number of samples kept between reading and writing in the ring buffer
D = 840  # display buffer size
N = round(D * H_SCALE_MAX) + SAFETY_MARGIN  # ring buffer size: enough for the most zoomed-out view


class Model:

    def __init__(self, adc: ADC = None):
        self.adc = adc
        self.ring_buffer = np.zeros(N, dtype=np.uint8)
        self.display_buffer = np.zeros(D, dtype=np.uint8)
        self.v_scale: float = 1.0
        self.v_scroll: int = 0
        self.h_scale: float = 1.0   # samples per pixel; range [H_SCALE_MIN, H_SCALE_MAX]
        self.h_scroll: int = 0
        self.write_head = np.array([0], dtype=np.int32)    # index in ring buffer (shared with other threads)
        self.trigger_idx = np.array([0], dtype=np.int32)   # index where trigger was detected (shared with other threads)
        self.trigger_level: int = 128
        self._stop_acquisition = False
        self._display_lock = threading.Lock()              # protects h_scale, h_scroll, v_scale, v_scroll
        self.fresh = np.array([True], dtype=bool)          # True when new trigger data is ready to display
        self.trigger_mode = 'auto'                         # 'auto' or 'normal'
        self.display_mean: float = 128.0                   # raw ADC mean used as anchor for v-transform
        self._recompute_mean: bool = True                  # set True by v_scale/v_scroll changes; cleared after one use

    # --- setters (acquire display lock internally so Display doesn't have to) ---

    def set_h_scale(self, value: float) -> None:
        with self._display_lock:
            self.h_scale = value

    def set_h_scroll(self, value: int) -> None:
        with self._display_lock:
            self.h_scroll = value

    def set_v_scale(self, value: float) -> None:
        with self._display_lock:
            self.v_scale = value
            self._recompute_mean = True

    def set_v_scroll(self, value: int) -> None:
        with self._display_lock:
            self.v_scroll = value
            self._recompute_mean = True

    def consume_fresh(self) -> bool:
        """Returns True if new trigger data is available. In normal mode, clears the flag."""
        if not self.fresh[0]:
            return False
        if self.trigger_mode == 'normal':
            self.fresh[0] = False
        return True

    # --- acquisition ---

    def stop_acquisition(self):
        """Signal the acquisition thread to stop."""
        self._stop_acquisition = True

    def fill_ring_buffer(self):
        """Acquisition thread: reads samples from serial and fills the ring buffer."""
        if self.adc is None:
            return

        previous_sample = np.uint8(0)  # last sample of previous chunk, for edge detection across chunk boundaries
        self._stop_acquisition = False

        while not self._stop_acquisition:
            try:
                raw = self.adc.read(self.adc.chunk_size)
                if not raw:
                    continue
                data = np.frombuffer(raw, dtype=np.uint8)
                n = len(data)
                start = self.write_head[0]
                space = N - start

                # write chunk into ring buffer, handling wrap-around
                if n <= space:
                    self.ring_buffer[start : start + n] = data
                else:
                    self.ring_buffer[start:] = data[:space]
                    self.ring_buffer[: n - space] = data[space:]

                # vectorized rising edge detection across the whole chunk;
                # prepend previous_sample so edges at index 0 of data are caught
                extended = np.empty(n + 1, dtype=np.uint8)
                extended[0] = previous_sample
                extended[1:] = data
                rising_edges = np.where(
                    (extended[:-1] < self.trigger_level) & (extended[1:] >= self.trigger_level)
                )[0]
                if rising_edges.size:
                    self.trigger_idx[0] = (start + rising_edges[-1]) % N
                    self.fresh[0] = True

                previous_sample = data[-1]
                self.write_head[0] = (start + n) % N  # single atomic update after chunk is written
            except Exception:
                pass

    # --- display buffer preparation ---

    def fill_display_buffer(self):
        """Read-only thread: extracts and processes data from ring buffer for display."""
        # snapshot the current scale/scroll values (with lock for thread safety)
        with self._display_lock:
            h_scale_snapshot  = self.h_scale
            h_scroll_snapshot = self.h_scroll
            v_scale_snapshot  = self.v_scale
            v_scroll_snapshot = self.v_scroll
            recompute_mean    = self._recompute_mean
            if recompute_mean:
                self._recompute_mean = False
        trigger_idx_snapshot = self.trigger_idx[0]
        

        samples_per_pixel = h_scale_snapshot
        effective_sample_count = round(D * samples_per_pixel)

        # calculate the start index in the ring buffer based on trigger index, h_scroll, and window size
        start_idx = (trigger_idx_snapshot + h_scroll_snapshot - effective_sample_count // 2)
        start_idx = np.clip(start_idx, trigger_idx_snapshot - effective_sample_count, trigger_idx_snapshot) % N
        end_idx = (start_idx + effective_sample_count) % N

        # wait until write_head has freshly written past end_idx
        end_offset   = (end_idx - trigger_idx_snapshot) % N
        write_offset = (self.write_head[0] - trigger_idx_snapshot) % N

        # sleep the time needed for the write head to pass end_idx, then busy-wait
        samples_needed = end_offset - write_offset
        if samples_needed > 0:
            sample_period = 1 / self.adc.sample_rate
            time.sleep(samples_needed * sample_period)

        while (self.write_head[0] - trigger_idx_snapshot) % N < end_offset:
            time.sleep(0)  # yield GIL to acquisition thread

        # head is past the end index; make sure it's not past the start index too
        start_offset = (start_idx - trigger_idx_snapshot) % N
        w_off = (self.write_head[0] - trigger_idx_snapshot) % N
        if w_off >= start_offset:
            print(f"CORRUPT: write past start by {(w_off - start_offset)} samples")
        else:
            print(f"OK: write head is {(start_offset - w_off)} samples before start")


        if start_idx < end_idx:
            samples = np.copy(self.ring_buffer[start_idx:end_idx])
        else:  # window wraps around the ring buffer
            samples = np.concatenate((self.ring_buffer[start_idx:], self.ring_buffer[:end_idx]))

        # resample the captured window to exactly D display pixels
        new_indices = np.linspace(0, effective_sample_count - 1, D)
        self.display_buffer = np.interp(new_indices, np.arange(effective_sample_count), samples).astype(np.uint8)

        # apply vertical scale (stretch around mean) and scroll (offset), clamp to uint8
        buf = self.display_buffer.astype(np.int16)
        if recompute_mean:
            self.display_mean = float(buf.mean())
        buf = (buf - self.display_mean) * v_scale_snapshot + self.display_mean + v_scroll_snapshot
        self.display_buffer = np.clip(buf, 0, 255).astype(np.uint8)
