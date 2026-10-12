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
from run_pyhrebsd import CONFIG, request_cancel, run, _open_reader, _path

CATEGORIES = {
    "Run and input": ["run_mode", "input_file", "output_dir", "generate_report", "report_format"],
    "Method and reference": ["analysis_method", "pattern_type", "h5_pc_source", "pc_mode", "material_name", "mechanical_constraint", "reference_map_point", "pattern_binning"],
    "Calibration": ["calibration_method", "calibration_line_extent_um", "calibration_line_spacing", "beam_shift_effective_pixel_size_um", "beam_shift_detector_x_sign"],
    "Geometry and PC": ["material_database", "detector_geometry", "reference_euler_degrees", "sample_tilt_degrees", "camera_elevation_degrees"],
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

class ConfigPage(QtWidgets.QWizardPage):
    def __init__(self, wizard, title, keys):
        super().__init__(); self.wizard = wizard; self.setTitle(title); self.field_rows = {}
        form = QtWidgets.QFormLayout(self); form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key in keys:
            if key not in CONFIG: continue
            editor = wizard.make_editor(key, CONFIG[key])
            label = QtWidgets.QLabel(key)
            form.addRow(label, editor)
            self.field_rows[key] = (label, editor)
            if key == "input_file": form.addRow("Pattern availability", wizard.pattern_status)
        self.setLayout(form)


class PyHREBSDWizard(QtWidgets.QWizard):
    def __init__(self):
        super().__init__(); self.setWindowTitle("pyHREBSD - Step-by-step wizard"); self.resize(1050, 760)
        self.widgets = {}; self.path_editors = {}; self.thread = None; self.worker = None; self.running = False
        self.pattern_status = QtWidgets.QLabel("Select an input file to inspect available pattern sets")
        self.pages = {}
        self.pages["input"] = ConfigPage(self, "Input file and run type", ["input_file", "output_dir", "run_mode", "generate_report", "report_format"])
        self.pages["method"] = ConfigPage(self, "Analysis method", ["analysis_method", "pattern_type", "h5_pc_source", "pc_mode", "material_name", "mechanical_constraint", "reference_map_point", "pattern_binning"])
        self.pages["calibration"] = ConfigPage(self, "Calibration", ["calibration_method", "calibration_line_extent_um", "calibration_line_spacing", "beam_shift_effective_pixel_size_um", "beam_shift_detector_x_sign"])
        self.pages["geometry"] = ConfigPage(self, "Geometry and pattern center", ["material_database", "detector_geometry", "reference_euler_degrees", "sample_tilt_degrees", "camera_elevation_degrees"])
        self.pages["execution"] = ConfigPage(self, "CPU execution", ["workers"])
        self.pages["roi"] = ConfigPage(self, "ROI settings", ["roi_device", "roi_gpu_device_id", "roi_gpu_workers", "gpu_batch_size", "roi_layout", "roi_size", "roi_size_percent", "roi_count", "roi_remapping", "roi_filter", "outlier_standard_deviation"])
        self.pages["homography"] = ConfigPage(self, "Homography settings", ["homography_device", "homography_gpu_device_id", "homography_gpu_workers", "homography_gpu_batch_size", "homography_margin_fraction", "homography_max_iterations", "homography_prealignment", "homography_prealignment_roi_count", "homography_prealignment_roi_size_percent", "homography_prealignment_roi_layout", "homography_warm_start"])
        self.pages["preprocess"] = ConfigPage(self, "Grains and raw-pattern correction", ["detect_grains", "grain_threshold_degrees", "grain_min_size", "grain_symmetry", "unprocessed_background_mode", "unprocessed_background_sigma_pixels", "unprocessed_background_downsample", "unprocessed_static_sigma_factor", "unprocessed_lmsd_factor"])
        self.pages["run"] = QtWidgets.QWizardPage(); self.pages["run"].setTitle("Run analysis")
        lay=QtWidgets.QVBoxLayout(self.pages["run"]); lay.addWidget(QtWidgets.QLabel("Review the configuration and click Run analysis.")); self.summary=QtWidgets.QPlainTextEdit(); self.summary.setReadOnly(True); lay.addWidget(self.summary)
        self.log=QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); lay.addWidget(self.log); self.progress=QtWidgets.QProgressBar(); self.progress.setRange(0,100); self.progress.hide(); lay.addWidget(self.progress)
        cancel=QtWidgets.QPushButton("Cancel analysis"); cancel.clicked.connect(self.cancel_run); lay.addWidget(cancel); self.cancel_button=cancel
        # QWizard assigns numeric page IDs when pages are added; retain those IDs for conditional routing.
        self.ids={}
        for key in ("input","method","calibration","geometry","execution","roi","homography","preprocess","run"):
            self.ids[key] = self.addPage(self.pages[key])
        self.setStartId(self.ids["input"]); self.pages["run"].setFinalPage(True)
        self.setButtonText(QtWidgets.QWizard.FinishButton,"Run analysis"); self.button(QtWidgets.QWizard.FinishButton).clicked.connect(self.accept)
        self.button(QtWidgets.QWizard.BackButton).clicked.connect(self.update_summary); self.button(QtWidgets.QWizard.NextButton).clicked.connect(self.update_summary)
        self.cancel_button.setEnabled(False); self.detect_gpu_default(); self.refresh_file_capabilities(str(CONFIG.get("input_file","")))
        for key in ("pattern_type", "analysis_method"):
            self.widgets[key].currentTextChanged.connect(self.refresh_context_visibility)
        self.refresh_context_visibility()

    def nextId(self):
        key=self._page_key(self.currentId())
        if key=="input": return self.ids["calibration"] if self.widgets["run_mode"].currentText()=="calibration" else self.ids["method"]
        if key=="calibration": return self.ids["run"]
        if key=="method": return self.ids["geometry"]
        if key=="geometry": return self.ids["execution"]
        if key=="execution":
            return self.ids["homography"] if self.widgets["analysis_method"].currentText()=="homography" else self.ids["roi"]
        if key=="roi":
            return self.ids["preprocess"] if self.widgets["analysis_method"].currentText()=="roi" else self.ids["homography"]
        if key=="homography": return self.ids["preprocess"]
        if key=="preprocess": return self.ids["run"]
        return -1

    def _page_key(self, page_id):
        return next((k for k,v in self.ids.items() if v==page_id), "")

    def make_editor(self,key,value):
        if key in CHOICES:
            w=QtWidgets.QComboBox(); w.addItems(CHOICES[key]); w.setCurrentText(str(value)); w.currentTextChanged.connect(self.update_summary); self.widgets[key]=w; return w
        if isinstance(value,bool):
            w=QtWidgets.QCheckBox(); w.setChecked(value); w.stateChanged.connect(self.update_summary); self.widgets[key]=w; return w
        w=QtWidgets.QLineEdit(); w.setText(json.dumps(value) if value is None or not isinstance(value,str) else value); w.editingFinished.connect(self.update_summary)
        if key in PATH_KEYS:
            b=QtWidgets.QPushButton("Browse"); b.clicked.connect(lambda: self.browse(key,w)); box=QtWidgets.QWidget(); l=QtWidgets.QHBoxLayout(box); l.setContentsMargins(0,0,0,0); l.addWidget(w); l.addWidget(b); self.widgets[key]=w; self.path_editors[key]=w
            if key=="input_file": w.editingFinished.connect(lambda: self.refresh_file_capabilities(w.text()))
            return box
        self.widgets[key]=w; return w

    def browse(self,key,editor):
        value=QtWidgets.QFileDialog.getExistingDirectory(self,"Select output folder") if key=="output_dir" else QtWidgets.QFileDialog.getOpenFileName(self,"Select file")[0]
        if value: editor.setText(value); self.refresh_file_capabilities(value) if key=="input_file" else None

    def value(self,key,w):
        if isinstance(w,QtWidgets.QCheckBox): return w.isChecked()
        text=w.currentText() if isinstance(w,QtWidgets.QComboBox) else w.text(); original=CONFIG.get(key)
        if original is None or isinstance(original,(bool,int,float,tuple,list,dict)):
            if text.strip().lower() in ("","none","null"): return None
            try: return json.loads(text)
            except json.JSONDecodeError as exc: raise ValueError(f"{key} must be valid JSON") from exc
        return text

    def config(self): return {k:self.value(k,w) for k,w in self.widgets.items()}
    def update_summary(self):
        try: self.summary.setPlainText(json.dumps(self.config(),indent=2))
        except ValueError: pass

    def refresh_file_capabilities(self,filename):
        if "pattern_type" not in self.widgets: return
        combo=self.widgets["pattern_type"]; path=Path(filename.strip().strip('"')) if filename else None; available={"processed","unprocessed"}; detail="processed and unprocessed available"
        try:
            suffix=path.suffix.lower() if path else ""
            if suffix==".h5oina":
                available=set()
                with h5py.File(path,"r") as f:
                    groups=[o for o in f.values() if isinstance(o,h5py.Group) and "EBSD/Data" in o]
                    if groups:
                        data=groups[0]["EBSD/Data"]; available={x for x,n in (("processed","Processed Patterns"),("unprocessed","Unprocessed Patterns")) if n in data}
                detail=", ".join(sorted(available)) or "no pattern dataset found"
            elif suffix in (".ang",".up2",".oh5",".tfs",".hdf5"): available={"processed"}; detail="processed only for this input format"
        except Exception as exc: available={"processed"}; detail=f"cannot inspect file ({exc})"
        for i in range(combo.count()): combo.model().item(i).setEnabled(combo.itemText(i) in available)
        if combo.currentText() not in available and available: combo.setCurrentText("processed" if "processed" in available else next(iter(available)))
        self.pattern_status.setText(detail)
        self.refresh_geometry_fields(path)

    def refresh_geometry_fields(self, path):
        """Hide geometry overrides when the selected reader supplies metadata."""
        page = self.pages.get("geometry")
        if page is None:
            return
        for key in ("sample_tilt_degrees", "camera_elevation_degrees"):
            row = page.field_rows.get(key)
            if row:
                row[0].setVisible(True)
                row[1].setVisible(True)
        if not path or not path.exists():
            return
        try:
            with _open_reader(path, self.config()) as reader:
                if reader.sample_tilt_degrees() is not None:
                    label, editor = page.field_rows["sample_tilt_degrees"]
                    label.setVisible(False); editor.setVisible(False)
                if reader.camera_elevation_degrees() is not None:
                    label, editor = page.field_rows["camera_elevation_degrees"]
                    label.setVisible(False); editor.setVisible(False)
                # Dataset readers provide the reference crystal orientation from
                # their Euler dataset; the manual override is only for image mode.
                try:
                    reader.orientation(0)
                except Exception:
                    pass
                else:
                    label, editor = page.field_rows["reference_euler_degrees"]
                    label.setVisible(False); editor.setVisible(False)
        except Exception:
            # Keep overrides available if the file is incomplete or still being edited.
            return

    def refresh_context_visibility(self):
        """Keep only settings that apply to the current input and method."""
        raw = self.widgets.get("pattern_type")
        raw_enabled = bool(raw and raw.currentText() == "unprocessed")
        page = self.pages.get("preprocess")
        if page:
            for key in ("unprocessed_background_mode", "unprocessed_background_sigma_pixels",
                        "unprocessed_background_downsample", "unprocessed_static_sigma_factor",
                        "unprocessed_lmsd_factor"):
                row = page.field_rows.get(key)
                if row:
                    row[0].setVisible(raw_enabled); row[1].setVisible(raw_enabled)
        method = self.widgets.get("analysis_method")
        method_name = method.currentText() if method else "roi"
        prealign = self.widgets.get("homography_prealignment")
        prealign_row = self.pages["homography"].field_rows.get("homography_prealignment")
        if prealign is not None and method_name == "hybrid":
            prealign.setCurrentText("roi_remap")
        if prealign_row:
            prealign_row[0].setVisible(method_name != "hybrid")
            prealign_row[1].setVisible(method_name != "hybrid")

    def detect_gpu_default(self):
        try:
            import cupy as cp
            count = int(cp.cuda.runtime.getDeviceCount())
        except Exception:
            count = 0
        for key in ("roi_device", "homography_device"):
            combo = self.widgets.get(key)
            if combo is None:
                continue
            gpu_item = combo.findText("gpu")
            if gpu_item >= 0:
                combo.model().item(gpu_item).setEnabled(count > 0)
            if count > 0:
                combo.setCurrentText("gpu")
            elif combo.currentText() == "gpu":
                combo.setCurrentText("cpu")
        if count > 0:
            for k in ("roi_gpu_workers", "homography_gpu_workers", "workers"):
                self.widgets.get(k).setText("1")

    def accept(self):
        if self.running: return
        try: config=self.config()
        except ValueError as exc: QtWidgets.QMessageBox.critical(self,"Configuration error",str(exc)); return
        self.running=True; self.cancel_button.setEnabled(True); self.button(QtWidgets.QWizard.FinishButton).setEnabled(False); self.log.clear(); self.progress.show(); self.progress.setValue(0); self.worker=RunWorker(config); self.thread=QtCore.QThread(self); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.execute); self.worker.message.connect(self.message); self.worker.finished.connect(self.run_finished); self.worker.failed.connect(self.run_failed); self.worker.finished.connect(self.thread.quit); self.worker.failed.connect(self.thread.quit); self.thread.finished.connect(self.cleanup); self.thread.start()

    def message(self,text):
        self.log.appendPlainText(text); import re; m=re.search(r"Processed\s+(\d+)/(\d+)\s+patterns",text)
        if m: self.progress.setRange(0,int(m.group(2))); self.progress.setValue(int(m.group(1)))

    def cancel_run(self):
        if self.running: request_cancel(); self.cancel_button.setEnabled(False); self.log.appendPlainText("Cancellation requested...")
    def run_finished(self,_): self.progress.setValue(self.progress.maximum()); self.log.appendPlainText("Analysis finished."); self.running=False; self.button(QtWidgets.QWizard.FinishButton).setText("Close"); self.button(QtWidgets.QWizard.FinishButton).setEnabled(True)
    def run_failed(self,msg): self.log.appendPlainText(msg); QtWidgets.QMessageBox.critical(self,"Analysis failed",msg); self.running=False; self.button(QtWidgets.QWizard.FinishButton).setEnabled(True)
    def cleanup(self): self.progress.hide(); self.cancel_button.setEnabled(False); self.worker=None; self.thread.deleteLater(); self.thread=None


def main():
    app=QtWidgets.QApplication(sys.argv); app.setApplicationName("pyHREBSD"); window=PyHREBSDWizard(); window.show(); sys.exit(app.exec())

if __name__ == "__main__": main()




