import os
os.environ["QT_SCALE_FACTOR"] = "2"  # must be before QApplication — fixes HiDPI on Linux, remove if unnecessary

import sys
import math
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore

from model import Model, D, H_SCALE_MIN, H_SCALE_MAX


class Display:
    def __init__(self, model: Model):
        self._model = model
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

        # --- top-level window ---
        self.win = QtWidgets.QWidget()
        self.win.setWindowTitle("Oscilloscope")
        main_layout = QtWidgets.QHBoxLayout(self.win)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # left pane: plot + div bar
        left_pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(left_pane)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(left_pane, stretch=1)

        # --- waveform plot (black) ---
        self._plot = pg.PlotWidget()
        self._plot.setBackground("#000000")
        self._plot.setYRange(0, 256, padding=0)
        self._plot.setXRange(0, D,   padding=0)
        self._plot.disableAutoRange()
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.getAxis("left").hide()
        self._plot.getAxis("bottom").hide()

        self._add_grid()
        self._curve = self._plot.plot(
            np.zeros(D, dtype=np.float32),
            pen=pg.mkPen("#00cc44", width=2),
        )

        self._trigger_line = pg.InfiniteLine(
            pos=model.trigger_level, angle=0,
            pen=pg.mkPen("#ff6600", width=1, style=QtCore.Qt.PenStyle.DashLine),
            movable=False,
        )
        self._trigger_line.setVisible(False)
        self._plot.addItem(self._trigger_line)

        self._trigger_text = pg.TextItem(anchor=(0, 1), color="#ff6600")
        self._trigger_text.setVisible(False)
        self._plot.addItem(self._trigger_text)

        self._level_line = pg.InfiniteLine(
            pos=128, angle=0,
            pen=pg.mkPen("#00aaff", width=1, style=QtCore.Qt.PenStyle.DashLine),
            movable=False,
        )
        self._level_line.setVisible(False)
        self._plot.addItem(self._level_line)

        self._level_text = pg.TextItem(anchor=(1, 1), color="#00aaff")
        self._level_text.setVisible(False)
        self._plot.addItem(self._level_text)

        layout.addWidget(self._plot, stretch=1)  # goes into left pane

        # --- div label row (black background, sits just below the plot) ---
        div_bar = QtWidgets.QWidget()
        div_bar.setStyleSheet("background-color: #000000;")
        div_row = QtWidgets.QHBoxLayout(div_bar)
        div_row.setContentsMargins(10, 2, 10, 2)

        label_style = "color: #aaaaaa; font-size: 20px; font-family: sans-serif;"
        self._volts_label = QtWidgets.QLabel()
        self._volts_label.setStyleSheet(label_style)
        self._volts_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self._time_label = QtWidgets.QLabel()
        self._time_label.setStyleSheet(label_style)
        self._time_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        div_row.addWidget(self._volts_label)
        div_row.addWidget(self._time_label)
        layout.addWidget(div_bar)  # goes into left pane

        # --- controls panel (gray casing) ---
        controls = QtWidgets.QWidget()
        controls.setStyleSheet(
            "QWidget { background-color: #4a4a4a; }"
            "QLabel  { color: #dddddd; font-size: 20px; background-color: transparent; }"
            "QComboBox { font-size: 20px; color: #dddddd; background-color: #3a3a3a; }"
        )
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.setSpacing(8)

        _group_style = (
            "QGroupBox {"
            "  border: 2px solid #888888;"
            "  border-radius: 4px;"
            "  margin-top: 14px;"
            "  padding: 4px;"
            "  font-size: 18px;"
            "  font-weight: bold;"
            "  color: #ffffff;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  left: 10px;"
            "  padding: 0 4px;"
            "  background-color: #4a4a4a;"
            "}"
        )

        def _make_group(title):
            box = QtWidgets.QGroupBox(title)
            box.setStyleSheet(_group_style)
            lay = QtWidgets.QVBoxLayout(box)
            lay.setContentsMargins(4, 10, 4, 6)
            lay.setSpacing(4)
            return box, lay

        # --- Horizontal group ---
        h_group, h_lay = _make_group("Horizontal")
        h_lay.addLayout(self._make_float_slider(
            label="H Scale",
            default_f=model.h_scale,
            on_change=self._on_h_scale_changed,
            store_as="_h_scale_value_label",
            to_float=lambda i: 10 ** (math.log10(H_SCALE_MIN) + i / 1000 * (math.log10(H_SCALE_MAX) - math.log10(H_SCALE_MIN))),
            to_int=lambda f: round((math.log10(f) - math.log10(H_SCALE_MIN)) / (math.log10(H_SCALE_MAX) - math.log10(H_SCALE_MIN)) * 1000),
            fmt="{:.2f}",
        ))
        h_lay.addLayout(self._make_slider(
            label="H Scroll",
            lo=-D, hi=D, default=model.h_scroll,
            on_change=self._on_h_scroll_changed,
            store_as="_h_scroll_value_label",
            slider_store_as="_h_scroll_slider",
        ))
        controls_layout.addWidget(h_group)

        # --- Vertical group ---
        v_group, v_lay = _make_group("Vertical")
        v_lay.addLayout(self._make_float_slider(
            label="V Scale",
            default_f=model.v_scale,
            on_change=self._on_v_scale_changed,
            store_as="_v_scale_value_label",
            to_float=lambda i: 1.0 + i / 1000 * 7.0,
            to_int=lambda f: round((f - 1.0) / 7.0 * 1000),
            fmt="{:.1f}",
        ))
        v_lay.addLayout(self._make_slider(
            label="V Scroll",
            lo=-127, hi=127, default=model.v_scroll,
            on_change=self._on_v_scroll_changed,
            store_as="_v_scroll_value_label",
        ))
        controls_layout.addWidget(v_group)

        # --- Trigger & Level group ---
        tl_group, tl_lay = _make_group("")
        tl_lay.addLayout(self._make_slider(
            label="Trigger",
            lo=0, hi=255, default=model.trigger_level,
            on_change=self._on_trigger_changed,
            store_as="_trigger_value_label",
            slider_store_as="_trigger_slider",
        ))
        self._trigger_slider.sliderPressed.connect(self._on_trigger_pressed)
        self._trigger_slider.sliderReleased.connect(self._on_trigger_released)

        # --- level indicator row ---
        level_row = QtWidgets.QHBoxLayout()
        level_row.setSpacing(4)
        self._level_checkbox = QtWidgets.QCheckBox()
        self._level_checkbox.setChecked(False)
        self._level_checkbox.toggled.connect(self._on_level_toggled)
        level_lbl = QtWidgets.QLabel("Level:")
        level_lbl.setFixedWidth(148)
        level_lbl.setStyleSheet("color: #dddddd;")
        self._level_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._level_slider.setRange(0, 255)
        self._level_slider.setValue(128)
        self._level_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self._level_slider.setTickInterval(25)
        self._level_slider.setMinimumHeight(40)
        self._level_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 8px; margin: 12px 0; }"
            "QSlider::handle:horizontal { width: 28px; height: 28px; margin: -10px 0; background: #00aaff; }"
        )
        self._level_value_label = QtWidgets.QLabel(str(self._level_slider.value()))
        self._level_value_label.setFixedWidth(80)
        self._level_slider.valueChanged.connect(self._on_level_changed)
        level_row.addWidget(self._level_checkbox)
        level_row.addWidget(level_lbl)
        level_row.addWidget(self._level_slider)
        level_row.addWidget(self._level_value_label)
        tl_lay.addLayout(level_row)

        # --- trigger mode ---
        trigger_mode_row = QtWidgets.QHBoxLayout()
        tm_lbl = QtWidgets.QLabel("Trigger Mode:")
        tm_lbl.setFixedWidth(180)
        self._trigger_mode_combo = QtWidgets.QComboBox()
        self._trigger_mode_combo.addItems(["auto", "normal"])
        self._trigger_mode_combo.setCurrentText(model.trigger_mode)
        self._trigger_mode_combo.setMinimumWidth(180)
        self._trigger_mode_combo.currentTextChanged.connect(self._on_trigger_mode_changed)
        trigger_mode_row.addWidget(tm_lbl)
        trigger_mode_row.addWidget(self._trigger_mode_combo)
        trigger_mode_row.addStretch()
        tl_lay.addLayout(trigger_mode_row)
        controls_layout.addWidget(tl_group)

        controls_layout.addStretch()  # push everything up, leave dead space at bottom
        controls.setMinimumWidth(620)
        main_layout.addWidget(controls)  # right pane

        self._update_div_labels()
        self.win.showMaximized()

    # --- helpers ---

    def _make_slider(self, label, lo, hi, default, on_change, store_as, slider_store_as=None):
        row = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(f"{label}:")
        lbl.setFixedWidth(180)
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(default)
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(max(1, (hi - lo) // 10))
        slider.setMinimumHeight(50)
        slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 8px; margin: 12px 0; }"
            "QSlider::handle:horizontal { width: 28px; height: 28px; margin: -10px 0; }"
        )
        val_label = QtWidgets.QLabel(str(default))
        val_label.setFixedWidth(80)
        slider.valueChanged.connect(on_change)
        setattr(self, store_as, val_label)
        if slider_store_as:
            setattr(self, slider_store_as, slider)
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_label)
        return row

    def _make_float_slider(self, label, default_f, on_change, store_as,
                            slider_store_as=None, to_float=None, to_int=None, fmt="{:.2f}"):
        """Like _make_slider but maps a 0–1000 integer slider to floats via to_float/to_int."""
        row = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(f"{label}:")
        lbl.setFixedWidth(180)
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(to_int(default_f))
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(100)
        slider.setMinimumHeight(50)
        slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 8px; margin: 12px 0; }"
            "QSlider::handle:horizontal { width: 28px; height: 28px; margin: -10px 0; }"
        )
        val_label = QtWidgets.QLabel(fmt.format(default_f))
        val_label.setFixedWidth(80)
        slider.valueChanged.connect(lambda i: on_change(to_float(i)))
        setattr(self, store_as, val_label)
        if slider_store_as:
            setattr(self, slider_store_as, slider)
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_label)
        return row

    def _add_grid(self):
        grid_pen = pg.mkPen(color="#2a2a2a", width=2)
        for y in range(32, 256, 32):
            line = pg.InfiniteLine(pos=y, angle=0, pen=grid_pen, movable=False)
            line.setZValue(-1)
            self._plot.addItem(line)
        for i in range(1, 10):
            line = pg.InfiniteLine(pos=D * i / 10, angle=90, pen=grid_pen, movable=False)
            line.setZValue(-1)
            self._plot.addItem(line)

    # --- slot handlers ---

    def _h_scroll_limits(self) -> int:
        spp = self._model.h_scale
        return round(D * spp) // 2

    def _on_h_scale_changed(self, value):
        self._model.set_h_scale(value)
        self._h_scale_value_label.setText(f"{value:.2f}")
        limit = self._h_scroll_limits()
        self._h_scroll_slider.setRange(-limit, limit)
        self._h_scroll_slider.setTickInterval(max(1, limit // 5))
        clamped = int(np.clip(self._model.h_scroll, -limit, limit))
        if clamped != self._model.h_scroll:
            self._h_scroll_slider.setValue(clamped)

    def _on_h_scroll_changed(self, value):
        self._model.set_h_scroll(value)
        self._h_scroll_value_label.setText(str(value))

    def _on_v_scale_changed(self, value):
        self._model.set_v_scale(value)
        self._v_scale_value_label.setText(f"{value:.2f}")

    def _on_v_scroll_changed(self, value):
        self._model.set_v_scroll(value)
        self._v_scroll_value_label.setText(str(value))

    def _on_trigger_changed(self, value):
        self._model.trigger_level = value
        self._trigger_value_label.setText(str(value))
        if self._trigger_line.isVisible():
            self._update_trigger_overlay()

    def _on_trigger_pressed(self):
        self._trigger_line.setVisible(True)
        self._trigger_text.setVisible(True)
        self._update_trigger_overlay()

    def _on_trigger_released(self):
        self._trigger_line.setVisible(False)
        self._trigger_text.setVisible(False)

    def _on_trigger_mode_changed(self, text):
        self._model.trigger_mode = text

    def _on_level_changed(self, value):
        self._level_value_label.setText(str(value))
        if self._level_line.isVisible():
            self._update_level_overlay()

    def _on_level_toggled(self, checked):
        self._level_line.setVisible(checked)
        self._level_text.setVisible(checked)
        if checked:
            self._update_level_overlay()

    def _update_trigger_overlay(self):
        mean = self._model.display_mean
        v_scale = self._model.v_scale
        v_scroll = self._model.v_scroll
        trig = self._model.trigger_level
        y_plot = float(np.clip((trig - mean) * v_scale + mean + v_scroll, 0, 255))
        self._trigger_line.setPos(y_plot)
        trigger_volts = trig / 255 * self._model.adc.voltage_range
        self._trigger_text.setPos(0, y_plot)
        self._trigger_text.setText(f"{trigger_volts:.3f} V")

    def _update_level_overlay(self):
        mean = self._model.display_mean
        v_scale = self._model.v_scale
        v_scroll = self._model.v_scroll
        level = self._level_slider.value()
        y_plot = float(np.clip((level - mean) * v_scale + mean + v_scroll, 0, 255))
        self._level_line.setPos(y_plot)
        level_volts = level / 255 * self._model.adc.voltage_range
        self._level_text.setPos(D, y_plot)
        self._level_text.setText(f"{level_volts:.3f} V")

    def _screen_voltage_range(self):
        """Returns (v_bottom_volts, v_top_volts) for the current viewport."""
        mean = self._model.display_mean
        v_scale = self._model.v_scale
        v_scroll = self._model.v_scroll
        y_raw_bottom = max(0.0, min(255.0, (0   - mean - v_scroll) / v_scale + mean))
        y_raw_top    = max(0.0, min(255.0, (255 - mean - v_scroll) / v_scale + mean))
        voltage_range = self._model.adc.voltage_range
        return y_raw_bottom / 255 * voltage_range, y_raw_top / 255 * voltage_range

    # --- div label ---

    def _update_div_labels(self):
        spp = self._model.h_scale
        effective = round(D * spp)
        adc = self._model.adc
        sample_rate = adc.sample_rate if adc is not None else 1
        voltage_range = adc.voltage_range if adc is not None else 5.0
        time_per_div = effective / (sample_rate * 10)
        volts_per_div = voltage_range / (8 * self._model.v_scale)
        self._volts_label.setText(self._fmt_volts(volts_per_div))
        self._time_label.setText(self._fmt_time(time_per_div))

    def _fmt_time(self, seconds: float) -> str:
        if seconds < 1e-3:
            return f"{seconds * 1e6:.1f} µs/div"
        return f"{seconds * 1e3:.2f} ms/div"

    def _fmt_volts(self, volts: float) -> str:
        if volts < 1.0:
            return f"{volts * 1000:.0f} mV/div"
        return f"{volts:.3f} V/div"

    # --- called by main loop ---

    def update(self, data: np.ndarray):
        if self._model.consume_fresh():
            self._curve.setData(data.astype(np.float32))
            self._update_div_labels()
            if self._level_line.isVisible():
                self._update_level_overlay()
            self.app.processEvents()
