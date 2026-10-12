"""Optional PySide6 configuration GUI for PyHREBSD.

Run from the repository with::

    python pyhrebsd_gui.py

The GUI edits the complete CONFIG dictionary as JSON, so every command-line
option remains available without duplicating the analysis implementation.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as exc:  # pragma: no cover - exercised only without optional GUI dependency
    raise SystemExit("Install the optional GUI dependency first: pip install 'pyhrebsd[gui]'") from exc

from run_pyhrebsd import CONFIG, run


class _QtLogStream:
    def __init__(self, signal):
        self.signal = signal
    def write(self, text):
        text = text.strip()
        if text:
            self.signal.emit(text)
    def flush(self):
        pass


class RunWorker(QtCore.QObject):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    message = QtCore.Signal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    @QtCore.Slot()
    def execute(self):
        try:
            with redirect_stdout(_QtLogStream(self.message)):
                result = run(self.config)
            self.finished.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyHREBSD")
        self.resize(1100, 760)
        self.thread = None
        self.worker = None

        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self.editor.setPlainText(json.dumps(CONFIG, indent=2, default=str))

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.status = QtWidgets.QLabel("Ready")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        load = QtWidgets.QPushButton("Load JSON")
        load.clicked.connect(self.load_json)
        save = QtWidgets.QPushButton("Save JSON")
        save.clicked.connect(self.save_json)
        run_button = QtWidgets.QPushButton("Run analysis")
        run_button.setDefault(True)
        run_button.clicked.connect(self.start_run)
        open_report = QtWidgets.QPushButton("Open report")
        open_report.clicked.connect(self.open_report)
        open_folder = QtWidgets.QPushButton("Open output folder")
        open_folder.clicked.connect(self.open_output_folder)

        buttons = QtWidgets.QHBoxLayout()
        for widget in (load, save, run_button, open_report, open_folder):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        buttons.addWidget(self.status)
        buttons.addWidget(self.progress)

        help_text = QtWidgets.QLabel(
            "Edit any CONFIG option as JSON. Paths may be absolute or relative to the repository. "
            "The analysis runs in a worker thread so the window remains responsive.")
        help_text.setWordWrap(True)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(help_text)
        layout.addLayout(buttons)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.log)
        splitter.setSizes([560, 160])
        layout.addWidget(splitter)
        central = QtWidgets.QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _json(self):
        try:
            value = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("The top-level JSON value must be an object")
        return value

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load configuration", "", "JSON (*.json)")
        if path:
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8"))
            self.status.setText(f"Loaded {Path(path).name}")

    def save_json(self):
        try:
            config = self._json()
        except ValueError as exc:
            QtWidgets.QMessageBox.critical(self, "Configuration error", str(exc)); return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save configuration", "pyhrebsd_config.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
            self.status.setText(f"Saved {Path(path).name}")

    def start_run(self):
        try:
            config = self._json()
        except ValueError as exc:
            QtWidgets.QMessageBox.critical(self, "Configuration error", str(exc)); return
        self.log.clear(); self.status.setText("Running"); self.progress.setVisible(True)
        self.thread = QtCore.QThread(self)
        self.worker = RunWorker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.execute)
        self.worker.finished.connect(self.run_finished)
        self.worker.failed.connect(self.run_failed)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.run_cleanup)
        self.thread.start()

    @QtCore.Slot(object)
    def run_finished(self, result):
        self.status.setText("Finished")
        self.log.appendPlainText("Analysis finished.")
        output = self._output_path()
        if output:
            self.log.appendPlainText(f"Results: {output}")

    @QtCore.Slot(str)
    def run_failed(self, message):
        self.status.setText("Failed")
        self.log.appendPlainText(message)
        QtWidgets.QMessageBox.critical(self, "Analysis failed", message)

    def run_cleanup(self):
        self.progress.setVisible(False)
        self.worker = None
        self.thread.deleteLater()
        self.thread = None

    def _output_path(self):
        try:
            config = self._json()
            return Path(config["output_dir"]).resolve()
        except Exception:
            return None

    def open_report(self):
        output = self._output_path()
        report = output / "report.html" if output else None
        if report and report.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(report)))
        else:
            QtWidgets.QMessageBox.information(self, "Report", "No report.html found in the configured output folder.")

    def open_output_folder(self):
        output = self._output_path()
        if output:
            output.mkdir(parents=True, exist_ok=True)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(output)))


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("pyHREBSD")
    window = MainWindow(); window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
