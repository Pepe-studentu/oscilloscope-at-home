import sys
import argparse
import time
import threading
import serial
from pyqtgraph.Qt import QtCore

from adc import ADC, FakeSerial
from model import Model
from display import Display


class AppRunner:
    """Owns the acquisition thread and the Qt display timer."""

    def __init__(self, model: Model, display: Display):
        self._model = model
        self._display = display
        self._fill_thread = None

    def start(self) -> QtCore.QTimer:
        acq = threading.Thread(target=self._model.fill_ring_buffer, daemon=True)
        acq.start()
        timer = QtCore.QTimer()
        timer.timeout.connect(self._on_timer)
        timer.start(33)  # ~30 FPS
        return timer

    def _on_timer(self):
        if self._fill_thread is not None:
            self._fill_thread.join()
            self._display.update(self._model.display_buffer)
        self._fill_thread = threading.Thread(
            target=self._model.fill_display_buffer, daemon=True
        )
        self._fill_thread.start()


parser = argparse.ArgumentParser(description="Oscilloscope - Display 8-bit serial ADC data in real-time")
parser.add_argument('--port', help='Serial port, e.g. /dev/ttyACM0 (omit to use simulated data)')
parser.add_argument('--sps', type=int, default=38461, help='Sampling rate in samples per second (default: 38461)')
parser.add_argument('--adc-range', type=float, default=5.0, help='ADC full-scale voltage (default: 5.0V)')
parser.add_argument('--chunk-size', type=int, default=256, help='Samples per read (default: 256)')
args = parser.parse_args()

if args.port:
    ser = serial.Serial(args.port, baudrate=args.sps, timeout=1)
    time.sleep(0.5)
    ser.reset_input_buffer()
    adc = ADC(ser, voltage_range=args.adc_range, chunk_size=args.chunk_size)
else:
    adc = ADC(FakeSerial(), voltage_range=args.adc_range, chunk_size=args.chunk_size)

model = Model(adc=adc)
display = Display(model)
runner = AppRunner(model, display)
timer = runner.start()  # keep reference so Qt doesn't GC the timer

sys.exit(display.app.exec())
