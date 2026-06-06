"""Native participant Focus Mode launcher for prepared PPS sessions."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
from pathlib import Path
from typing import Any

from .app_assets import apply_qt_app_icon, set_windows_app_user_model_id
from .session_runner import SessionRunnerController, load_run_package


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run native PPS Focus Mode from a prepared session manifest.")
    parser.add_argument("--session-manifest", type=Path, required=True, help="Path to local_data/sessions/.../session_manifest.json.")
    return parser


def _require_qt() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
    except ImportError as exc:
        raise RuntimeError("Install the GUI extra to run native Focus Mode: pip install -e .[gui]") from exc
    return {
        "QApplication": QApplication,
        "QDialog": QDialog,
        "QHBoxLayout": QHBoxLayout,
        "QIcon": QIcon,
        "QLabel": QLabel,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QTimer": QTimer,
        "QVBoxLayout": QVBoxLayout,
        "Qt": Qt,
    }


def run_focus_window(session_manifest: Path) -> int:
    q = _require_qt()
    package = load_run_package(session_manifest)
    set_windows_app_user_model_id("PPS.Toolkit.FocusMode")
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])

    dialog = q["QDialog"]()
    dialog.setWindowTitle(f"PPS Focus Mode - {package.participant_id}")
    dialog.setModal(True)
    dialog.resize(960, 640)
    apply_qt_app_icon(q, app=app, window=dialog)
    dialog.setStyleSheet(
        """
        QWidget {
            background: #101312;
            color: #f1f5f2;
            font-family: "Aptos", "Noto Sans", sans-serif;
            font-size: 12pt;
        }
        QLabel {
            background: transparent;
        }
        QProgressBar {
            border: 1px solid #3e4b46;
            border-radius: 6px;
            background: #171d1a;
            height: 18px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: #3aa786;
            border-radius: 5px;
        }
        QPushButton {
            background: #18201d;
            border: 1px solid #3e4b46;
            border-radius: 8px;
            color: #f1f5f2;
            padding: 10px 14px;
        }
        QPushButton:hover {
            background: #22302b;
            border-color: #5f766e;
        }
        QPushButton#targetButton {
            background: #e9eee8;
            color: #101312;
            border-color: #e9eee8;
            font-size: 22pt;
            font-weight: 700;
        }
        QPushButton#targetButton:hover {
            background: #ffffff;
        }
        """
    )

    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    title = q["QLabel"](f"Participant {package.participant_id}")
    title.setAlignment(q["Qt"].AlignmentFlag.AlignCenter)
    layout.addWidget(title)

    progress_label = q["QLabel"]("Ready")
    progress_label.setAlignment(q["Qt"].AlignmentFlag.AlignCenter)
    layout.addWidget(progress_label)

    progress = q["QProgressBar"]()
    progress.setRange(0, 1000)
    progress.setValue(0)
    layout.addWidget(progress)

    target = q["QPushButton"]("Click")
    target.setObjectName("targetButton")
    target.setMinimumHeight(260)
    layout.addWidget(target, 1)

    controls = q["QHBoxLayout"]()
    pause_button = q["QPushButton"]("Pause")
    stop_button = q["QPushButton"]("Stop")
    controls.addStretch(1)
    controls.addWidget(pause_button)
    controls.addWidget(stop_button)
    controls.addStretch(1)
    layout.addLayout(controls)

    messages: queue.Queue[tuple[str, Any]] = queue.Queue()
    controller = SessionRunnerController(package)

    def _run() -> None:
        result = controller.run(
            progress_callback=lambda payload: messages.put(("progress", payload)),
            event_callback=lambda message: messages.put(("event", message)),
        )
        messages.put(("done", result))

    def _click() -> None:
        controller.log_click(in_target=True)

    def _toggle_pause() -> None:
        if pause_button.text() == "Pause":
            controller.pause()
            pause_button.setText("Resume")
            progress_label.setText("Paused")
        else:
            controller.resume()
            pause_button.setText("Pause")

    def _stop() -> None:
        controller.stop()
        progress_label.setText("Stopping")

    target.clicked.connect(_click)
    pause_button.clicked.connect(_toggle_pause)
    stop_button.clicked.connect(_stop)

    timer = q["QTimer"](dialog)
    exit_code = {"value": 1}

    def _drain() -> None:
        while not messages.empty():
            kind, payload = messages.get_nowait()
            if kind == "progress":
                duration = float(payload.get("duration_s") or 0.0)
                elapsed = float(payload.get("elapsed_s") or 0.0)
                value = int(max(0.0, min(1.0, elapsed / duration)) * 1000) if duration > 0 else 0
                progress.setValue(value)
                progress_label.setText(
                    f"Block {payload.get('block_index')}: {payload.get('block_label')}  {elapsed:.1f}/{duration:.1f}s"
                )
            elif kind == "event":
                progress_label.setText(str(payload))
            elif kind == "done":
                exit_code["value"] = 0 if payload.completed else 2
                progress_label.setText("Complete" if payload.completed else "Interrupted")
                timer.stop()
                dialog.accept()

    timer.timeout.connect(_drain)
    timer.start(100)
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    if hasattr(dialog, "showFullScreen"):
        dialog.showFullScreen()
    dialog.exec()
    return int(exit_code["value"])


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_focus_window(args.session_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
