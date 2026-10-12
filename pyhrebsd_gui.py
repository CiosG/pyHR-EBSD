"""Optional PySide6 GUI for configuring and running pyHREBSD."""
from __future__ import annotations
import json, sys, traceback, re
import h5py
from contextlib import redirect_stdout
from pathlib import Path
try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as exc:
    raise SystemExit("Install the optional GUI dependency first: pip install 'pyhrebsd[gui]'") from exc
from run_pyhrebsd import CONFIG, run

CATEGORIES = {
    "Run and input": ["run_mode", "input_file", "output_dir", "generate_report", "report_format"],
    "Method and reference": ["analysis_method", "pattern_type", "h5_pc_source", "pc_mode", "material_name", "mechanical_constraint", "reference_map_point", "pattern_binning"],
    "Calibration": ["calibration_method", "calibration_line_extent_um", "calibration_line_spacing", "beam_shift_effective_pixel_size_um", "beam_shift_detector_x_sign"],
    "Geometry and PC": ["material_database", "pattern_center_fallback", "detector_geometry", "reference_euler_degrees", "sample_tilt_degrees", "camera_elevation_degrees"],
    "Execution and output": ["workers", "save_per_pattern_files", "uncertainty_pc_shift_pixels"],
    "ROI": ["roi_device", "roi_gpu_device_id", "roi_gpu_workers", "gpu_batch_size", "roi_layout", "roi_size", "roi_size_percent", "roi_count", "roi_remapping", "roi_filter", "outlier_standard_deviation"],
    "Homography": ["homography_device", "homography_gpu_device_id", "homography_gpu_workers", "homography_gpu_batch_size", "homography_margin_fraction", "homography_max_iterations", "homography_prealignment", "homography_prealignment_roi_count", "homography_prealignment_roi_size_percent", "homography_prealignment_roi_layout", "homography_warm_start"],
    "Grains and preprocessing": ["detect_grains", "grain_threshold_degrees", "grain_min_size", "grain_symmetry", "unprocessed_background_mode", "unprocessed_background_sigma_pixels", "unprocessed_background_downsample", "unprocessed_static_sigma_factor", "unprocessed_lmsd_factor"],
}
CHOICES = {
    "run_mode": ["analysis", "calibration"], "analysis_method": ["roi", "homography", "hybrid"],
    "pattern_type": ["processed", "unprocessed"], "h5_pc_source": ["ebsd", "data_processing"],
    "pc_mode": ["array", "single", "beam_shift_eps"], "mechanical_constraint": ["traction_free", "isochoric"],
    "report_format": ["html", "pdf", "both"], "calibration_method": ["roi", "homography"],
    "beam_shift_detector_x_sign": ["auto", "-1", "1"], "detector_geometry": ["full", "elevation"],
    "roi_device": ["cpu", "gpu"], "roi_layout": ["annular", "grid"], "homography_device": ["cpu", "gpu"],
    "homography_prealignment": ["none", "roi_remap"], "homography_prealignment_roi_layout": ["annular", "grid"],
    "grain_symmetry": ["cubic", "none"], "unprocessed_background_mode": ["static_lmsd", "dynamic_lmsd", "divide_gaussian", "subtract_gaussian", "none"],
}
PATH_KEYS = {"input_file", "output_dir", "material_database", "edax_up2_file", "edax_ang_file"}

class _QtLogStream:
    def __init__(self, signal): self.signal = signal
    def write(self, text):
        if text.strip(): self.signal.emit(text.strip())
    def flush(self): pass

class RunWorker(QtCore.QObject):
    finished = QtCore.Signal(object); failed = QtCore.Signal(str); message = QtCore.Signal(str)
    def __init__(self, config): super().__init__(); self.config = config
    @QtCore.Slot()
    def execute(self):
        try:
            with redirect_stdout(_QtLogStream(self.message)): result = run(self.config)
            self.finished.emit(result)
        except Exception: self.failed.emit(traceback.format_exc())

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("pyHREBSD"); self.resize(1120, 820)
        self.widgets = {}; self.path_editors = {}; self.thread = None; self.worker = None
        self.pattern_status = QtWidgets.QLabel("Select an input file to inspect available pattern sets")
        self.tabs = QtWidgets.QTabWidget()
        used = set()
        for category, keys in CATEGORIES.items():
            page = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(page); form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            for key in keys:
                if key not in CONFIG: continue
                used.add(key); form.addRow(key, self._make_editor(key, CONFIG[key]))
                if category == "Run and input" and key == "input_file": form.addRow("Pattern availability", self.pattern_status)
            scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.tabs.addTab(scroll, category)
        advanced = QtWidgets.QWidget(); advanced_layout = QtWidgets.QVBoxLayout(advanced)
        self.raw = QtWidgets.QPlainTextEdit(); self.raw.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)); advanced_layout.addWidget(self.raw)
        apply_raw = QtWidgets.QPushButton("Apply JSON to form"); apply_raw.clicked.connect(self.apply_raw); advanced_layout.addWidget(apply_raw)
        self.tabs.addTab(advanced, "Advanced JSON")
        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(5000)
        load = QtWidgets.QPushButton("Load JSON"); load.clicked.connect(self.load_json)
        save = QtWidgets.QPushButton("Save JSON"); save.clicked.connect(self.save_json)
        run_button = QtWidgets.QPushButton("Run analysis"); run_button.clicked.connect(self.start_run)
        report = QtWidgets.QPushButton("Open report"); report.clicked.connect(self.open_report)
        folder = QtWidgets.QPushButton("Open output folder"); folder.clicked.connect(self.open_folder)
        self.status = QtWidgets.QLabel("Ready"); self.progress = QtWidgets.QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setMinimumWidth(220); self.progress.hide()
        buttons = QtWidgets.QHBoxLayout()
        for b in (load, save, run_button, report, folder): buttons.addWidget(b)
        buttons.addStretch(); buttons.addWidget(self.status); buttons.addWidget(self.progress)
        central = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(central); layout.addLayout(buttons); layout.addWidget(self.tabs); layout.addWidget(self.log); self.setCentralWidget(central)
        self.sync_raw()
        self.refresh_file_capabilities(str(CONFIG.get("input_file", "")))
        self.detect_gpu_default()

    def detect_gpu_default(self):
        """Use GPU as the GUI default only when CuPy can see a CUDA device."""
        try:
            import cupy as cp
            count = int(cp.cuda.runtime.getDeviceCount())
        except Exception:
            count = 0
        if count > 0:
            for key in ("roi_device", "homography_device"):
                widget = self.widgets.get(key)
                if isinstance(widget, QtWidgets.QComboBox): widget.setCurrentText("gpu")
            for key in ("roi_gpu_device_id", "homography_gpu_device_id"):
                widget = self.widgets.get(key)
                if isinstance(widget, QtWidgets.QLineEdit): widget.setText("0")
            self.status.setText(f"GPU detected ({count} device(s)); GPU selected")
        else:
            self.status.setText("GPU not detected; CPU selected")
        self.sync_raw()

    def _make_editor(self, key, value):
        if key in CHOICES:
            w = QtWidgets.QComboBox(); w.addItems(CHOICES[key]); w.setCurrentText(str(value)); w.currentTextChanged.connect(self.sync_raw); self.widgets[key] = w; return w
        if isinstance(value, bool):
            w = QtWidgets.QCheckBox(); w.setChecked(value); w.stateChanged.connect(self.sync_raw); self.widgets[key] = w; return w
        w = QtWidgets.QLineEdit(); w.setText(json.dumps(value) if value is None or not isinstance(value, str) else value); w.editingFinished.connect(self.sync_raw)
        if key in PATH_KEYS:
            browse = QtWidgets.QPushButton("Browse")
            browse.clicked.connect(lambda: self.browse(key, w))
            box = QtWidgets.QWidget(); lay = QtWidgets.QHBoxLayout(box); lay.setContentsMargins(0,0,0,0); lay.addWidget(w); lay.addWidget(browse); self.widgets[key] = w; self.path_editors[key] = w
            if key == "input_file": w.editingFinished.connect(lambda: self.refresh_file_capabilities(w.text()))
            return box
        self.widgets[key] = w; return w

    def browse(self, key, editor):
        if key == "output_dir": value = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        else: value, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file")
        if value:
            editor.setText(value); self.sync_raw()
            if key == "input_file": self.refresh_file_capabilities(value)

    def refresh_file_capabilities(self, filename):
        combo = self.widgets.get("pattern_type")
        if combo is None: return
        path = Path(filename.strip().strip('"')) if filename else None
        available = {"processed", "unprocessed"}; detail = "processed and unprocessed available"
        try:
            suffix = path.suffix.lower() if path else ""
            if suffix == ".h5oina":
                available = set()
                with h5py.File(path, "r") as file:
                    groups = [obj for obj in file.values() if isinstance(obj, h5py.Group) and "EBSD/Data" in obj]
                    if groups:
                        data = groups[0]["EBSD/Data"]
                        if "Processed Patterns" in data: available.add("processed")
                        if "Unprocessed Patterns" in data: available.add("unprocessed")
                detail = ", ".join(sorted(available)) or "no pattern dataset found"
            elif suffix in (".ang", ".up2", ".oh5", ".tfs", ".hdf5"):
                available = {"processed"}; detail = "processed only for this input format"
            elif suffix == ".bcf": detail = "processed and unprocessed selected by BCF reader"
            elif path and not path.exists(): detail = "file not found yet"
        except Exception as exc:
            available = {"processed"}; detail = f"cannot inspect file ({exc})"
        for i in range(combo.count()): combo.model().item(i).setEnabled(combo.itemText(i) in available)
        if combo.currentText() not in available and available:
            combo.setCurrentText("processed" if "processed" in available else next(iter(available)))
        self.pattern_status.setText(detail); self.pattern_status.setToolTip("Available pattern datasets: " + detail)

    def value(self, key, widget):
        if isinstance(widget, QtWidgets.QCheckBox): return widget.isChecked()
        text = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text()
        original = CONFIG.get(key)
        if original is None or isinstance(original, (bool, int, float, tuple, list, dict)):
            if text.strip().lower() in ("", "none", "null"): return None
            try: return json.loads(text)
            except json.JSONDecodeError: raise ValueError(f"{key} must be valid JSON, for example 1, null, or [1, 2]")
        return text

    def config(self):
        result = {}
        for key, widget in self.widgets.items(): result[key] = self.value(key, widget)
        return result

    def sync_raw(self):
        try: self.raw.setPlainText(json.dumps(self.config(), indent=2))
        except ValueError: pass

    def apply_raw(self):
        try: self.set_config(json.loads(self.raw.toPlainText()))
        except Exception as exc: QtWidgets.QMessageBox.critical(self, "Configuration error", str(exc))

    def set_config(self, config):
        for key, value in config.items():
            w = self.widgets.get(key)
            if w is None: continue
            blocker = QtCore.QSignalBlocker(w)
            if isinstance(w, QtWidgets.QCheckBox): w.setChecked(bool(value))
            elif isinstance(w, QtWidgets.QComboBox): w.setCurrentText(str(value))
            else: w.setText(json.dumps(value) if value is None or not isinstance(value, str) else value)
            del blocker
        self.sync_raw()
        self.refresh_file_capabilities(str(config.get("input_file", "")))

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load configuration", "", "JSON (*.json)")
        if path: self.set_config(json.loads(Path(path).read_text(encoding="utf-8"))); self.status.setText(f"Loaded {Path(path).name}")

    def save_json(self):
        try: config = self.config()
        except ValueError as exc: QtWidgets.QMessageBox.critical(self, "Configuration error", str(exc)); return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save configuration", "pyhrebsd_config.json", "JSON (*.json)")
        if path: Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8"); self.status.setText(f"Saved {Path(path).name}")

    def start_run(self):
        try: config = self.config()
        except ValueError as exc: QtWidgets.QMessageBox.critical(self, "Configuration error", str(exc)); return
        self.log.clear(); self.status.setText("Running"); self.progress.show(); self.thread = QtCore.QThread(self); self.worker = RunWorker(config); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.execute); self.worker.message.connect(self.handle_message); self.worker.finished.connect(self.finished); self.worker.failed.connect(self.failed); self.worker.finished.connect(self.thread.quit); self.worker.failed.connect(self.thread.quit); self.thread.finished.connect(self.cleanup); self.thread.start()

    @QtCore.Slot(str)
    def handle_message(self, message):
        self.log.appendPlainText(message)
        match = re.search(r"Processed\s+(\d+)/(\d+)\s+patterns", message)
        if match:
            done, total = map(int, match.groups())
            self.progress.setRange(0, max(1, total)); self.progress.setValue(done)
            self.status.setText(f"Processed {done}/{total} patterns")
        elif message.startswith("ROIs") or message.startswith("Homography") or message.startswith("Geometry"):
            self.status.setText(message[:100])

    def finished(self, _): self.progress.setValue(self.progress.maximum()); self.status.setText("Finished"); self.log.appendPlainText("Analysis finished.")
    def failed(self, message): self.status.setText("Failed"); self.log.appendPlainText(message); QtWidgets.QMessageBox.critical(self, "Analysis failed", message)
    def cleanup(self): self.progress.hide(); self.worker = None; self.thread.deleteLater(); self.thread = None
    def output(self):
        try: return Path(self.config()["output_dir"]).resolve()
        except Exception: return None
    def open_report(self):
        p = self.output(); report = p / "report.html" if p else None
        if report and report.exists(): QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(report)))
        else: QtWidgets.QMessageBox.information(self, "Report", "No report.html found in the configured output folder.")
    def open_folder(self):
        p = self.output()
        if p: p.mkdir(parents=True, exist_ok=True); QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(p)))

def main():
    app = QtWidgets.QApplication(sys.argv); app.setApplicationName("pyHREBSD"); window = MainWindow(); window.show(); sys.exit(app.exec())
if __name__ == "__main__": main()
