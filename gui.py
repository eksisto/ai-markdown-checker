#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主程序，GUI 版
"""

from __future__ import annotations

import json
import sys
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from checker_add import GitDiffExtractor
from checker_ai import initialize_client, get_ai_response
from checker_process_markdown import extract_text_from_markdown, split_into_sentences, write_to_txt
from clear_output_cache import clear_output_cache
from checker import (
    ensure_output_dir,
    load_change_out,
    load_filtered_change_lines,
    parse_label,
    split_label as split_label_with_tag,
    replace_sentence_in_file,
    load_review_progress,
    save_review_progress,
    clear_review_progress,
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

REQUIRED_CONFIG_KEYS = [
    "SYSTEM_PROMPT",
    "OLLAMA_MODEL",
    "REQUEST_DELAY_SECONDS",
]


def load_config() -> Dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(config: Dict[str, object]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_posts_dir(config: Dict[str, object]) -> Path:
    posts = config.get("POSTS_DIR")
    if isinstance(posts, str) and posts.strip():
        return (BASE_DIR / posts).resolve()
    return (BASE_DIR / "posts").resolve()


def validate_config(config: Dict[str, object]) -> Tuple[bool, str]:
    missing = [k for k in REQUIRED_CONFIG_KEYS if not config.get(k)]
    if missing:
        return False, f"缺少配置项：{', '.join(missing)}"
    return True, ""


class ThemeManager(QtCore.QObject):
    theme_changed = QtCore.Signal()

    def __init__(self, app: QtWidgets.QApplication) -> None:
        super().__init__()
        self._app = app
        self._mode = "system"
        self._system_scheme = self._read_system_scheme()

    def _read_system_scheme(self) -> str:
        try:
            scheme = QtGui.QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == QtCore.Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.apply()

    def enable_system_tracking(self) -> None:
        hints = QtGui.QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    def _on_system_scheme_changed(self, scheme: QtCore.Qt.ColorScheme) -> None:
        self._system_scheme = "dark" if scheme == QtCore.Qt.ColorScheme.Dark else "light"
        if self._mode == "system":
            self.apply()

    def current_scheme(self) -> str:
        if self._mode == "system":
            return self._system_scheme
        return self._mode

    def apply(self) -> None:
        scheme = self.current_scheme()
        self._app.setStyleSheet(build_qss(scheme))
        self.theme_changed.emit()


class DiffHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document: QtGui.QTextDocument, theme_manager: ThemeManager) -> None:
        super().__init__(document)
        self.theme_manager = theme_manager
        self.theme_manager.theme_changed.connect(self.rehighlight)

    def highlightBlock(self, text: str) -> None:
        scheme = self.theme_manager.current_scheme()
        if scheme == "dark":
            added_color = QtGui.QColor("#2ea44f")
            removed_color = QtGui.QColor("#da3633")
            header_color = QtGui.QColor("#8b949e")
            chunk_color = QtGui.QColor("#79c0ff")
        else:
            added_color = QtGui.QColor("#28a745")
            removed_color = QtGui.QColor("#d73a49")
            header_color = QtGui.QColor("#586069")
            chunk_color = QtGui.QColor("#005cc5")

        if text.startswith("+"):
            if text.startswith("+++"):
                self.setFormat(0, len(text), header_color)
            else:
                self.setFormat(0, len(text), added_color)
        elif text.startswith("-"):
            if text.startswith("---"):
                self.setFormat(0, len(text), header_color)
            else:
                self.setFormat(0, len(text), removed_color)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), chunk_color)
        elif text.startswith("diff"):
            self.setFormat(0, len(text), header_color)


THEME_COLORS: Dict[str, Dict[str, str]] = {
    "light": {
        "app_bg_start": "#f7f8fa",
        "app_bg_end": "#eef2f6",
        "text_primary": "#1b1d21",
        "text_muted": "#5a5f6a",
        "card_bg": "#ffffff",
        "card_border": "#d7dde5",
        "input_bg": "#ffffff",
        "input_border": "#cfd6df",
        "focus_border": "#0f6cbd",
        "dropdown_bg": "#f3f6fa",
        "combo_view_bg": "#ffffff",
        "combo_view_border": "#cfd6df",
        "selection_bg": "#e6f0fb",
        "selection_text": "#1b1d21",
        "button_bg": "#0f6cbd",
        "button_text": "#ffffff",
        "button_disabled_bg": "#9fbad6",
        "button_disabled_text": "#ffffff",
        "ghost_text": "#0f6cbd",
        "ghost_border": "#cfd6df",
        "danger_bg": "#c53b3b",
        "danger_text": "#ffffff",
        "tab_text": "#3a3f48",
        "tab_active_text": "#0f6cbd",
        "progress_bg": "#eef2f6",
        "progress_border": "#d7dde5",
        "progress_text": "#3a3f48",
        "progress_chunk": "#0f6cbd",
        "list_bg": "#ffffff",
        "list_border": "#d7dde5",
        "checkbox_text": "#1b1d21",
        "checkbox_bg": "#ffffff",
        "checkbox_border": "#cfd6df",
        "checkbox_checked_bg": "#0f6cbd",
        "checkbox_checked_border": "#0f6cbd",
        "tab_indicator": "#0f6cbd",
    },
    "dark": {
        "app_bg_start": "#1e1f24",
        "app_bg_end": "#2a2d33",
        "text_primary": "#f0f2f5",
        "text_muted": "#9aa0aa",
        "card_bg": "#2b2f36",
        "card_border": "#3a404a",
        "input_bg": "#262a30",
        "input_border": "#3a404a",
        "focus_border": "#4f9dff",
        "dropdown_bg": "#2f353d",
        "combo_view_bg": "#262a30",
        "combo_view_border": "#3a404a",
        "selection_bg": "#33465c",
        "selection_text": "#f0f2f5",
        "button_bg": "#4f9dff",
        "button_text": "#0b111a",
        "button_disabled_bg": "#5b6b7a",
        "button_disabled_text": "#c0c7d1",
        "ghost_text": "#cdd6e1",
        "ghost_border": "#3a404a",
        "danger_bg": "#d15252",
        "danger_text": "#0b111a",
        "tab_text": "#c7ccd5",
        "tab_active_text": "#4f9dff",
        "progress_bg": "#23262b",
        "progress_border": "#3a404a",
        "progress_text": "#c7ccd5",
        "progress_chunk": "#4f9dff",
        "list_bg": "#2b2f36",
        "list_border": "#3a404a",
        "checkbox_text": "#f0f2f5",
        "checkbox_bg": "#262a30",
        "checkbox_border": "#3a404a",
        "checkbox_checked_bg": "#4f9dff",
        "checkbox_checked_border": "#4f9dff",
        "tab_indicator": "#4f9dff",
    },
}

LIGHT_QSS_TEMPLATE = """
QWidget#AppRoot {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {app_bg_start}, stop:1 {app_bg_end});
    color: {text_primary};
}}
QLabel#TitleLabel {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel {{
    color: {text_primary};
}}
QLabel#SubtitleLabel {{
    color: {text_muted};
}}
QFrame#Card {{
    background: {card_bg};
    border: 1px solid {card_border};
    border-radius: 10px;
}}
QDialog, QMessageBox {{
    background: {card_bg};
    color: {text_primary};
}}
QMessageBox QLabel {{
    color: {text_primary};
}}
QMessageBox QTextEdit, QMessageBox QTextBrowser {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 6px;
    color: {text_primary};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 8px;
    padding: 6px 8px;
    color: {text_primary};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {focus_border};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {input_border};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: {dropdown_bg};
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {combo_view_border};
    border-radius: 0;
    background: {combo_view_bg};
    color: {text_primary};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    outline: 0;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 8px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    image: none;
}}
QPushButton {{
    background: {button_bg};
    color: {button_text};
    border: none;
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:disabled {{
    background: {button_disabled_bg};
    color: {button_disabled_text};
}}
QPushButton#GhostButton {{
    background: transparent;
    color: {ghost_text};
    border: 1px solid {ghost_border};
}}
QPushButton#DestructiveButton {{
    background: {danger_bg};
    color: {danger_text};
}}
QTabWidget::pane {{
    border: none;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 16px;
    margin-right: 8px;
    border-bottom: 2px solid transparent;
    color: {tab_text};
}}
QTabBar::tab:selected {{
    border-bottom: 2px solid transparent;
    color: {tab_active_text};
}}
QProgressBar {{
    background: {progress_bg};
    border: 1px solid {progress_border};
    border-radius: 6px;
    height: 14px;
    text-align: center;
    color: {progress_text};
}}
QProgressBar::chunk {{
    background: {progress_chunk};
    border-radius: 6px;
}}
QListWidget {{
    background: {list_bg};
    border: 1px solid {list_border};
    border-radius: 10px;
    color: {text_primary};
}}
QCheckBox {{
    spacing: 6px;
    color: {checkbox_text};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {checkbox_border};
    background: {checkbox_bg};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {checkbox_checked_border};
    background: {checkbox_checked_bg};
}}
"""

DARK_QSS_TEMPLATE = """
QWidget#AppRoot {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {app_bg_start}, stop:1 {app_bg_end});
    color: {text_primary};
}}
QLabel#TitleLabel {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel {{
    color: {text_primary};
}}
QLabel#SubtitleLabel {{
    color: {text_muted};
}}
QFrame#Card {{
    background: {card_bg};
    border: 1px solid {card_border};
    border-radius: 10px;
}}
QDialog, QMessageBox {{
    background: {card_bg};
    color: {text_primary};
}}
QMessageBox QLabel {{
    color: {text_primary};
}}
QMessageBox QTextEdit, QMessageBox QTextBrowser {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 6px;
    color: {text_primary};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {input_bg};
    border: 1px solid {input_border};
    border-radius: 8px;
    padding: 6px 8px;
    color: {text_primary};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {focus_border};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {input_border};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: {dropdown_bg};
}}
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {combo_view_border};
    border-radius: 0;
    background: {combo_view_bg};
    color: {text_primary};
    selection-color: {selection_text};
    selection-background-color: {selection_bg};
    outline: 0;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 8px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    image: none;
}}
QPushButton {{
    background: {button_bg};
    color: {button_text};
    border: none;
    border-radius: 8px;
    padding: 5px 12px;
}}
QPushButton:disabled {{
    background: {button_disabled_bg};
    color: {button_disabled_text};
}}
QPushButton#GhostButton {{
    background: transparent;
    color: {ghost_text};
    border: 1px solid {ghost_border};
}}
QPushButton#DestructiveButton {{
    background: {danger_bg};
    color: {danger_text};
}}
QTabWidget::pane {{
    border: none;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 16px;
    margin-right: 8px;
    border-bottom: 2px solid transparent;
    color: {tab_text};
}}
QTabBar::tab:selected {{
    border-bottom: 2px solid transparent;
    color: {tab_active_text};
}}
QProgressBar {{
    background: {progress_bg};
    border: 1px solid {progress_border};
    border-radius: 6px;
    height: 14px;
    text-align: center;
    color: {progress_text};
}}
QProgressBar::chunk {{
    background: {progress_chunk};
    border-radius: 6px;
}}
QListWidget {{
    background: {list_bg};
    border: 1px solid {list_border};
    border-radius: 10px;
}}
QCheckBox {{
    spacing: 6px;
    color: {checkbox_text};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {checkbox_border};
    background: {checkbox_bg};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {checkbox_checked_border};
    background: {checkbox_checked_bg};
}}
"""


def get_theme_colors(scheme: str) -> Dict[str, str]:
    return THEME_COLORS.get(scheme, THEME_COLORS["light"])


def build_qss(scheme: str) -> str:
    colors = dict(get_theme_colors(scheme))
    colors["text_primary_uri"] = colors["text_primary"].replace("#", "%23")
    template = DARK_QSS_TEMPLATE if scheme == "dark" else LIGHT_QSS_TEMPLATE
    return template.format_map(colors)


class AiWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)
    prepared = QtCore.Signal(str, str, int)
    finished = QtCore.Signal(str, str)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        mode: str,
        config: Dict[str, object],
        posts_dir: Path,
        input_path: Optional[Path] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._config = config
        self._posts_dir = posts_dir
        self._input_path = input_path
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()

    def pause(self) -> None:
        self._pause_event.clear()
        self.log.emit("已暂停")

    def resume(self) -> None:
        self._pause_event.set()
        self.log.emit("已继续")

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()
        self.log.emit("正在停止...")

    def run(self) -> None:
        try:
            change_path, out_path = self._prepare_inputs()
            if self._stop_event.is_set():
                return
            lines = change_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                self.failed.emit("没有可处理的内容")
                return
            total = len(lines)
            self.prepared.emit(str(change_path), str(out_path), total)

            client = initialize_client(self._config)
            delay = float(self._config.get("REQUEST_DELAY_SECONDS", 0.1))

            with open(out_path, "w", encoding="utf-8") as f_out:
                for idx, raw_line in enumerate(lines, start=1):
                    if self._stop_event.is_set():
                        self.log.emit("已被用户停止")
                        break
                    self._wait_if_paused()
                    content = raw_line.strip()
                    label, content = split_label_with_tag(content)
                    if not content:
                        self.progress.emit(idx, total)
                        continue
                    result = get_ai_response(client, content, self._config)
                    f_out.write(f"{label}{result}\n")
                    f_out.flush()
                    self.progress.emit(idx, total)
                    time.sleep(delay)

            self.finished.emit(str(change_path), str(out_path))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _wait_if_paused(self) -> None:
        while not self._pause_event.is_set():
            if self._stop_event.is_set():
                return
            time.sleep(0.15)

    def _prepare_inputs(self) -> Tuple[Path, Path]:
        output_dir = ensure_output_dir()
        if self._mode == "git":
            self.log.emit(f"正在扫描 Git 变更：{self._posts_dir}")
            extractor = GitDiffExtractor(self._posts_dir)
            changes = extractor.extract_all_changes()
            if not changes:
                raise RuntimeError("未检测到 Git 变更")
            change_path = output_dir / "changes.txt"
            out_path = output_dir / "changes_out.txt"
            extractor.save_to_file(changes, change_path, include_metadata=True)
            return change_path, out_path

        if not self._input_path:
            raise RuntimeError("缺少输入文件")

        stem = self._input_path.stem
        change_path = output_dir / f"{stem}.txt"
        out_path = output_dir / f"{stem}_out.txt"
        self.log.emit(f"正在解析 Markdown: {self._input_path}")
        text_blocks = extract_text_from_markdown(str(self._input_path))
        sentences = split_into_sentences(text_blocks)
        write_to_txt(sentences, str(change_path), str(self._input_path))
        return change_path, out_path


class ReviewItem:
    def __init__(
        self,
        label: str,
        sentence: str,
        origin: str,
        suggestion: str,
        filename: str,
        error_type: str = "",
        description: str = "",
    ) -> None:
        self.label = label
        self.sentence = sentence
        self.origin = origin
        self.suggestion = suggestion
        self.filename = filename
        self.error_type = error_type
        self.description = description


class AnimatedTabBar(QtWidgets.QTabBar):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._indicator_pos = 0.0
        self._indicator_width = 0.0
        self._indicator_color = QtGui.QColor(
            THEME_COLORS["light"]["tab_indicator"])

        self._pos_anim = QtCore.QPropertyAnimation(self, b"indicatorPos", self)
        self._width_anim = QtCore.QPropertyAnimation(
            self, b"indicatorWidth", self)
        self._anim_group = QtCore.QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._pos_anim)
        self._anim_group.addAnimation(self._width_anim)
        self._pos_anim.setDuration(220)
        self._width_anim.setDuration(220)
        self._pos_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._width_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

    def set_indicator_color(self, color: QtGui.QColor) -> None:
        self._indicator_color = color
        self.update()

    def animate_to(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        rect = self.tabRect(index)
        if rect.isNull():
            return
        self._pos_anim.stop()
        self._width_anim.stop()
        self._pos_anim.setStartValue(self._indicator_pos)
        self._pos_anim.setEndValue(float(rect.x()))
        self._width_anim.setStartValue(self._indicator_width)
        self._width_anim.setEndValue(float(rect.width()))
        self._anim_group.start()

    def sync_indicator(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        rect = self.tabRect(index)
        if rect.isNull():
            return
        self._indicator_pos = float(rect.x())
        self._indicator_width = float(rect.width())
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.currentIndex() >= 0:
            self.sync_indicator(self.currentIndex())

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if self.count() == 0:
            return
        if self._indicator_width <= 0:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(self._indicator_color)
        pen.setWidth(2)
        painter.setPen(pen)
        y = self.height() - 1
        painter.drawLine(
            QtCore.QPointF(self._indicator_pos, y),
            QtCore.QPointF(self._indicator_pos + self._indicator_width, y),
        )
        painter.end()

    @QtCore.Property(float)
    def indicatorPos(self) -> float:
        return self._indicator_pos

    @indicatorPos.setter
    def indicatorPos(self, value: float) -> None:
        self._indicator_pos = value
        self.update()

    @QtCore.Property(float)
    def indicatorWidth(self) -> float:
        return self._indicator_width

    @indicatorWidth.setter
    def indicatorWidth(self, value: float) -> None:
        self._indicator_width = value
        self.update()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, theme_manager: ThemeManager) -> None:
        super().__init__()
        self.theme_manager = theme_manager
        self.setWindowTitle("AI Markdown Checker")
        self.setMinimumSize(1100, 850)

        self.config = load_config()
        self.posts_dir = get_posts_dir(self.config)

        self.worker: Optional[AiWorker] = None
        self.review_items: List[ReviewItem] = []
        self.failed_items: List[ReviewItem] = []
        self.review_index = 0
        self.review_md_cache: Dict[str, Path] = {}
        self._tab_fade_anim: Optional[QtCore.QPropertyAnimation] = None
        self._tab_bar: Optional[AnimatedTabBar] = None

        self._build_ui()
        self._refresh_config_ui()
        self._refresh_git_ui()

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        root.setObjectName("AppRoot")
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("AI Markdown Checker")
        title.setObjectName("TitleLabel")
        subtitle = QtWidgets.QLabel("调用 AI 对 Markdown 文档进行校对的工作台")
        subtitle.setObjectName("SubtitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        self.system_theme_check = QtWidgets.QCheckBox("跟随系统")
        self.system_theme_check.setChecked(True)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["浅色", "深色"])
        self.theme_combo.setEnabled(False)
        header.addWidget(self.system_theme_check)
        header.addWidget(self.theme_combo)

        layout.addLayout(header)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self._tab_bar = AnimatedTabBar()
        self.tabs.setTabBar(self._tab_bar)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.run_tab = self._build_run_tab()
        self.review_tab = self._build_review_tab()
        self.config_tab = self._build_config_tab()
        self.git_tab = self._build_git_tab()

        self.tabs.addTab(self.run_tab, "运行")
        self.tabs.addTab(self.review_tab, "审查")
        self.tabs.addTab(self.config_tab, "配置")
        self.tabs.addTab(self.git_tab, "Git")

        if self._tab_bar is not None:
            self._tab_bar.sync_indicator(self.tabs.currentIndex())

        layout.addWidget(self.tabs)
        self.setCentralWidget(root)

        self.system_theme_check.toggled.connect(self._on_theme_mode_change)
        self.theme_combo.currentTextChanged.connect(self._on_theme_mode_change)
        self.theme_manager.theme_changed.connect(
            self._apply_tab_indicator_color)
        self._apply_tab_indicator_color()

    def _on_tab_changed(self, index: int) -> None:
        if self._tab_bar is not None:
            self._tab_bar.animate_to(index)
        self._fade_in_tab(index)

    def _fade_in_tab(self, index: int) -> None:
        stack = self.tabs.findChild(QtWidgets.QStackedWidget)
        if not stack:
            return
        if self._tab_fade_anim is not None and self._tab_fade_anim.state() == QtCore.QAbstractAnimation.Running:
            self._tab_fade_anim.stop()
        width = stack.width()
        if width <= 0:
            return
        height = stack.height()
        new_widget = self.tabs.widget(index)
        if not new_widget:
            return

        stack.setUpdatesEnabled(False)
        new_widget.setGeometry(0, 0, width, height)
        new_widget.move(0, 0)
        new_widget.show()
        new_widget.raise_()

        effect = QtWidgets.QGraphicsOpacityEffect(new_widget)
        effect.setOpacity(0.0)
        new_widget.setGraphicsEffect(effect)

        anim = QtCore.QPropertyAnimation(effect, b"opacity", new_widget)
        anim.setDuration(360)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        def _finalize() -> None:
            new_widget.setGraphicsEffect(None)

        anim.finished.connect(_finalize)

        stack.setUpdatesEnabled(True)
        stack.update()

        self._tab_fade_anim = anim
        anim.start()

    def _apply_tab_indicator_color(self) -> None:
        if self._tab_bar is None:
            return
        scheme = self.theme_manager.current_scheme()
        colors = get_theme_colors(scheme)
        color = QtGui.QColor(colors["tab_indicator"])
        self._tab_bar.set_indicator_color(color)

    def _on_theme_mode_change(self, *_: object) -> None:
        if self.system_theme_check.isChecked():
            self.theme_combo.setEnabled(False)
            self.theme_manager.set_mode("system")
        else:
            self.theme_combo.setEnabled(True)
            mode = "dark" if self.theme_combo.currentText() == "深色" else "light"
            self.theme_manager.set_mode(mode)

    def _build_card(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        return frame

    def _configure_form_layout(self, form: QtWidgets.QFormLayout) -> None:
        form.setVerticalSpacing(5)
        form.setLabelAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

    def _build_run_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(16)

        mode_card = self._build_card()
        mode_layout = QtWidgets.QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(16, 14, 16, 14)
        mode_label = QtWidgets.QLabel("模式")
        mode_label.setObjectName("SubtitleLabel")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Git：已变更的 Markdown", "单个 Markdown 文件"])
        self.mode_combo.currentIndexChanged.connect(self._update_run_mode)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        layout.addWidget(mode_card)

        input_card = self._build_card()
        input_layout = QtWidgets.QFormLayout(input_card)
        input_layout.setContentsMargins(16, 14, 16, 14)
        self._configure_form_layout(input_layout)
        self.posts_dir_field = QtWidgets.QLineEdit()
        self.posts_dir_field.setReadOnly(True)
        self.input_file_field = QtWidgets.QLineEdit()
        self.input_browse_btn = QtWidgets.QPushButton("浏览")
        self.input_browse_btn.clicked.connect(self._choose_input_file)
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(10)
        input_row.addWidget(self.input_file_field)
        input_row.addWidget(self.input_browse_btn)

        input_layout.addRow("文章目录", self.posts_dir_field)
        input_layout.addRow("Markdown 文件", input_row)
        layout.addWidget(input_card)

        output_card = self._build_card()
        output_layout = QtWidgets.QFormLayout(output_card)
        output_layout.setContentsMargins(16, 14, 16, 14)
        self._configure_form_layout(output_layout)
        self.output_change_field = QtWidgets.QLineEdit()
        self.output_change_field.setReadOnly(True)
        self.output_out_field = QtWidgets.QLineEdit()
        self.output_out_field.setReadOnly(True)
        output_layout.addRow("Markdown 分句", self.output_change_field)
        output_layout.addRow("AI 输出", self.output_out_field)
        layout.addWidget(output_card)

        action_card = self._build_card()
        action_layout = QtWidgets.QHBoxLayout(action_card)
        action_layout.setContentsMargins(16, 14, 16, 14)
        self.start_btn = QtWidgets.QPushButton("开始")
        self.pause_btn = QtWidgets.QPushButton("暂停")
        self.resume_btn = QtWidgets.QPushButton("继续")
        self.stop_btn = QtWidgets.QPushButton("停止")
        self.clear_cache_btn = QtWidgets.QPushButton("清理输出缓存")
        self.clear_cache_btn.setObjectName("GhostButton")

        self.start_btn.clicked.connect(self._start_run)
        self.pause_btn.clicked.connect(self._pause_run)
        self.resume_btn.clicked.connect(self._resume_run)
        self.stop_btn.clicked.connect(self._stop_run)
        self.clear_cache_btn.clicked.connect(self._clear_cache)

        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.pause_btn)
        action_layout.addWidget(self.resume_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addStretch(1)
        action_layout.addWidget(self.clear_cache_btn)
        layout.addWidget(action_card)

        progress_card = self._build_card()
        progress_layout = QtWidgets.QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 14, 16, 14)
        self.progress_label = QtWidgets.QLabel("空闲")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_card)

        log_card = self._build_card()
        log_layout = QtWidgets.QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 14, 16, 14)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(QtWidgets.QLabel("日志"))
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_card, stretch=1)

        self._update_run_mode()
        return tab

    def _build_review_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(16)

        select_card = self._build_card()
        select_layout = QtWidgets.QFormLayout(select_card)
        select_layout.setContentsMargins(16, 14, 16, 14)
        self._configure_form_layout(select_layout)

        self.review_change_field = QtWidgets.QLineEdit()
        self.review_out_field = QtWidgets.QLineEdit()
        change_btn = QtWidgets.QPushButton("浏览")
        out_btn = QtWidgets.QPushButton("浏览")
        change_btn.clicked.connect(
            lambda: self._choose_review_file(self.review_change_field))
        out_btn.clicked.connect(
            lambda: self._choose_review_file(self.review_out_field))
        change_row = QtWidgets.QHBoxLayout()
        change_row.setSpacing(10)
        change_row.addWidget(self.review_change_field)
        change_row.addWidget(change_btn)
        out_row = QtWidgets.QHBoxLayout()
        out_row.setSpacing(10)
        out_row.addWidget(self.review_out_field)
        out_row.addWidget(out_btn)

        self.review_load_btn = QtWidgets.QPushButton("加载")
        self.review_load_btn.clicked.connect(self._load_review_data)

        select_layout.addRow("输入清单（*.txt）", change_row)
        select_layout.addRow("AI 输出（*_out.txt）", out_row)
        select_layout.addRow("", self.review_load_btn)
        layout.addWidget(select_card)

        content_layout = QtWidgets.QHBoxLayout()

        self.review_list = QtWidgets.QListWidget()
        self.review_list.currentRowChanged.connect(self._show_review_item)
        content_layout.addWidget(self.review_list, stretch=1)

        detail_card = self._build_card()
        detail_layout = QtWidgets.QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)

        self.review_progress_label = QtWidgets.QLabel("未加载任何条目")
        self.review_file_label = QtWidgets.QLabel("文件：-")
        self.review_error_type_label = QtWidgets.QLabel("错误类型：-")
        self.review_description_label = QtWidgets.QLabel("错误描述：-")

        self.review_origin = QtWidgets.QPlainTextEdit()
        self.review_origin.setReadOnly(True)
        self.review_suggestion = QtWidgets.QPlainTextEdit()
        self.review_suggestion.setReadOnly(True)
        self.review_edit = QtWidgets.QPlainTextEdit()

        action_row = QtWidgets.QHBoxLayout()
        self.use_suggestion_btn = QtWidgets.QPushButton("使用建议")
        self.apply_next_btn = QtWidgets.QPushButton("应用并下一条")
        self.skip_btn = QtWidgets.QPushButton("跳过")
        self.open_file_btn = QtWidgets.QPushButton("打开文件")
        self.open_file_btn.setObjectName("GhostButton")

        self.use_suggestion_btn.clicked.connect(self._use_suggestion)
        self.apply_next_btn.clicked.connect(self._apply_and_next)
        self.skip_btn.clicked.connect(self._skip_item)
        self.open_file_btn.clicked.connect(self._open_current_file)

        action_row.addWidget(self.use_suggestion_btn)
        action_row.addWidget(self.apply_next_btn)
        action_row.addWidget(self.skip_btn)
        action_row.addStretch(1)
        action_row.addWidget(self.open_file_btn)

        detail_layout.addWidget(self.review_progress_label)
        detail_layout.addWidget(self.review_file_label)
        detail_layout.addWidget(self.review_error_type_label)
        detail_layout.addWidget(self.review_description_label)
        detail_layout.addWidget(QtWidgets.QLabel("原文"))
        detail_layout.addWidget(self.review_origin)
        detail_layout.addWidget(QtWidgets.QLabel("建议"))
        detail_layout.addWidget(self.review_suggestion)
        detail_layout.addWidget(QtWidgets.QLabel("编辑"))
        detail_layout.addWidget(self.review_edit)
        detail_layout.addLayout(action_row)

        content_layout.addWidget(detail_card, stretch=2)
        layout.addLayout(content_layout, stretch=1)
        return tab

    def _build_config_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(16)

        card = self._build_card()
        form = QtWidgets.QFormLayout(card)
        form.setContentsMargins(16, 14, 16, 14)
        self._configure_form_layout(form)

        self.host_field = QtWidgets.QLineEdit()
        self.host_field.setPlaceholderText("http://localhost:11434")
        self.model_field = QtWidgets.QLineEdit()
        self.model_field.setPlaceholderText("qwen3:8b")
        self.delay_spin = QtWidgets.QDoubleSpinBox()
        self.delay_spin.setRange(0, 3600)
        self.delay_spin.setDecimals(2)
        self.delay_spin.setSingleStep(0.1)
        self.temperature_field = QtWidgets.QLineEdit()
        self.temperature_field.setPlaceholderText("1")
        self.top_p_field = QtWidgets.QLineEdit()
        self.top_p_field.setPlaceholderText("1")
        self.posts_dir_edit = QtWidgets.QLineEdit()
        self.posts_dir_btn = QtWidgets.QPushButton("浏览")
        self.posts_dir_btn.clicked.connect(self._choose_posts_dir)
        posts_row = QtWidgets.QHBoxLayout()
        posts_row.setSpacing(10)
        posts_row.addWidget(self.posts_dir_edit)
        posts_row.addWidget(self.posts_dir_btn)

        self.prompt_field = QtWidgets.QPlainTextEdit()
        form.addRow("Ollama 地址", self.host_field)
        form.addRow("模型", self.model_field)
        form.addRow("延迟（秒）", self.delay_spin)
        form.addRow("Temperature", self.temperature_field)
        form.addRow("Top P", self.top_p_field)
        form.addRow("文章目录", posts_row)
        form.addRow("提示词", self.prompt_field)

        layout.addWidget(card)

        action_row = QtWidgets.QHBoxLayout()
        self.config_save_btn = QtWidgets.QPushButton("保存配置")
        self.config_reload_btn = QtWidgets.QPushButton("重新加载")
        self.config_save_btn.clicked.connect(self._save_config_ui)
        self.config_reload_btn.clicked.connect(self._reload_config_ui)
        action_row.addWidget(self.config_save_btn)
        action_row.addWidget(self.config_reload_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        layout.addStretch(1)

        return tab

    def _build_git_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(16)

        info_card = self._build_card()
        info_layout = QtWidgets.QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 14, 16, 14)
        self.git_repo_label = QtWidgets.QLabel("仓库：-")
        info_layout.addWidget(self.git_repo_label)
        layout.addWidget(info_card)

        action_card = self._build_card()
        action_layout = QtWidgets.QHBoxLayout(action_card)
        action_layout.setContentsMargins(16, 14, 16, 14)
        self.git_refresh_btn = QtWidgets.QPushButton("刷新")
        self.git_init_btn = QtWidgets.QPushButton("初始化仓库")
        self.git_stage_btn = QtWidgets.QPushButton("全部暂存")
        self.git_commit_btn = QtWidgets.QPushButton("提交")
        self.git_commit_btn.setObjectName("DestructiveButton")

        self.git_refresh_btn.clicked.connect(self._refresh_git_ui)
        self.git_init_btn.clicked.connect(self._git_init_repo)
        self.git_stage_btn.clicked.connect(self._git_stage_all)
        self.git_commit_btn.clicked.connect(self._git_commit)

        action_layout.addWidget(self.git_refresh_btn)
        action_layout.addWidget(self.git_init_btn)
        action_layout.addWidget(self.git_stage_btn)
        action_layout.addWidget(self.git_commit_btn)
        action_layout.addStretch(1)
        layout.addWidget(action_card)

        msg_card = self._build_card()
        msg_layout = QtWidgets.QFormLayout(msg_card)
        msg_layout.setContentsMargins(16, 14, 16, 14)
        self._configure_form_layout(msg_layout)
        self.git_message_field = QtWidgets.QLineEdit()
        msg_layout.addRow("提交说明", self.git_message_field)
        layout.addWidget(msg_card)

        output_card = self._build_card()
        output_layout = QtWidgets.QVBoxLayout(output_card)
        output_layout.setContentsMargins(16, 14, 16, 14)

        self.git_output = QtWidgets.QPlainTextEdit()
        self.git_output.setReadOnly(True)
        self.git_output.setMaximumHeight(150)
        output_layout.addWidget(QtWidgets.QLabel("Git 状态"))
        output_layout.addWidget(self.git_output)

        self.git_diff_view = QtWidgets.QPlainTextEdit()
        self.git_diff_view.setReadOnly(True)
        self.git_diff_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        font = QtGui.QFont("Consolas", 10)
        if not font.exactMatch():
            font = QtGui.QFont("Courier New", 10)
        self.git_diff_view.setFont(font)
        self.diff_highlighter = DiffHighlighter(
            self.git_diff_view.document(), self.theme_manager)

        output_layout.addWidget(QtWidgets.QLabel("Git 差异"))
        output_layout.addWidget(self.git_diff_view, stretch=1)
        layout.addWidget(output_card, stretch=1)

        return tab

    def _update_run_mode(self) -> None:
        is_git = self.mode_combo.currentIndex() == 0
        self.posts_dir_field.setText(str(self.posts_dir))
        self.input_file_field.setEnabled(not is_git)
        self.input_browse_btn.setEnabled(not is_git)
        if is_git:
            self.output_change_field.setText(
                str(ensure_output_dir() / "changes.txt"))
            self.output_out_field.setText(
                str(ensure_output_dir() / "changes_out.txt"))
        else:
            path_text = self.input_file_field.text().strip()
            if path_text:
                stem = Path(path_text).stem
                self.output_change_field.setText(
                    str(ensure_output_dir() / f"{stem}.txt"))
                self.output_out_field.setText(
                    str(ensure_output_dir() / f"{stem}_out.txt"))
            else:
                self.output_change_field.setText("")
                self.output_out_field.setText("")

    def _choose_input_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 Markdown", str(self.posts_dir), "Markdown (*.md)"
        )
        if path:
            self.input_file_field.setText(path)
            self._update_run_mode()

    def _choose_posts_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择文章目录", str(self.posts_dir)
        )
        if path:
            self.posts_dir_edit.setText(path)

    def _start_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self._log("已有任务在运行")
            return
        ok, msg = validate_config(self.config)
        if not ok:
            QtWidgets.QMessageBox.warning(self, "配置", msg)
            return

        mode = "git" if self.mode_combo.currentIndex() == 0 else "single"
        input_path = None
        if mode == "single":
            text = self.input_file_field.text().strip()
            if not text:
                QtWidgets.QMessageBox.warning(self, "输入", "请选择 Markdown 文件")
                return
            input_path = Path(text)

        self.progress_bar.setValue(0)
        self.progress_label.setText("准备中...")
        self._log("开始任务")

        self.worker = AiWorker(mode, self.config, self.posts_dir, input_path)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._update_progress)
        self.worker.prepared.connect(self._on_prepared)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _pause_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.pause()

    def _resume_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.resume()

    def _stop_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def _on_prepared(self, change_path: str, out_path: str, total: int) -> None:
        self.output_change_field.setText(change_path)
        self.output_out_field.setText(out_path)
        self.progress_bar.setRange(0, total)
        self.progress_label.setText(f"处理中 0 / {total}")

    def _update_progress(self, current: int, total: int) -> None:
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"处理中 {current} / {total}")

    def _on_finished(self, change_path: str, out_path: str) -> None:
        self._log(f"完成。输出：{out_path}")
        self.progress_label.setText("已完成")
        self.worker = None
        self._populate_review_defaults(change_path, out_path)

    def _on_failed(self, message: str) -> None:
        self._log(f"失败：{message}")
        self.progress_label.setText("失败")
        self.worker = None

    def _clear_cache(self) -> None:
        removed = clear_output_cache(BASE_DIR)
        QtWidgets.QMessageBox.information(
            self, "缓存", f"已从输出中移除 {removed} 条记录"
        )

    def _log(self, message: str) -> None:
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def _populate_review_defaults(self, change_path: str, out_path: str) -> None:
        self.review_change_field.setText(change_path)
        self.review_out_field.setText(out_path)

    def _choose_review_file(self, field: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择文本文件", str(ensure_output_dir()), "文本 (*.txt)"
        )
        if path:
            field.setText(path)

    def _load_review_data(self) -> None:
        change_path_text = self.review_change_field.text().strip()
        out_path_text = self.review_out_field.text().strip()
        if not change_path_text or not out_path_text:
            QtWidgets.QMessageBox.warning(self, "审查", "请选择输入和输出文件")
            return

        change_path = Path(change_path_text)
        out_path = Path(out_path_text)
        if not change_path.exists() or not out_path.exists():
            QtWidgets.QMessageBox.warning(self, "审查", "所选文件不存在")
            return

        change_out_data = load_change_out(out_path)
        if not change_out_data:
            QtWidgets.QMessageBox.warning(self, "审查", "未找到 AI 输出条目")
            return

        filtered_lines = load_filtered_change_lines(
            change_path, set(change_out_data.keys()))
        if not filtered_lines:
            QtWidgets.QMessageBox.warning(self, "审查", "未找到匹配的标签")
            return

        self.review_items = []
        self.failed_items = []
        for label, sentence in filtered_lines:
            _, filename = parse_label(label)
            ai_info = change_out_data.get(label, {})
            origin = ai_info.get("original_text") or sentence
            suggestion = ai_info.get("checked_text") or ai_info.get("raw", "")
            error_type = ai_info.get("error_type", "")
            description = ai_info.get("description", "")
            self.review_items.append(ReviewItem(
                label, sentence, origin, suggestion, filename, error_type, description))

        self.review_list.clear()
        for item in self.review_items:
            preview = item.origin or item.sentence
            preview = preview[:60] + ("..." if len(preview) > 60 else "")
            list_item = QtWidgets.QListWidgetItem(
                f"{item.filename} | {preview}")
            self.review_list.addItem(list_item)

        self.review_md_cache.clear()
        self.review_index = 0
        progress_change, progress_out, progress_index = load_review_progress()
        if progress_change == str(change_path.resolve()) and progress_out == str(out_path.resolve()):
            if 0 <= progress_index < len(self.review_items):
                resume = QtWidgets.QMessageBox.question(
                    self,
                    "继续",
                    f"是否从第 {progress_index + 1} 条继续？",
                )
                if resume == QtWidgets.QMessageBox.StandardButton.Yes:
                    self.review_index = progress_index
                else:
                    clear_review_progress()

        self.review_list.setCurrentRow(self.review_index)
        self._show_review_item(self.review_index)

    def _show_review_item(self, index: int) -> None:
        if not self.review_items:
            self.review_progress_label.setText("未加载任何条目")
            return
        if index < 0 or index >= len(self.review_items):
            return

        self.review_index = index
        item = self.review_items[index]

        # 预检查：句子是否在原文件中存在
        md_path = self._resolve_md_path(item.filename)
        found = False
        if md_path:
            try:
                content = md_path.read_text(encoding="utf-8")
                if item.sentence in content:
                    found = True
            except Exception:
                pass

        if not found:
            # 如果没找到，记录并自动跳转到下一条
            if not any(f.label == item.label for f in self.failed_items):
                self.failed_items.append(item)
            QtCore.QTimer.singleShot(0, self._advance_review)
            return

        self.review_progress_label.setText(
            f"第 {index + 1} 条 / 共 {len(self.review_items)} 条")
        self.review_file_label.setText(f"文件：{item.filename}")
        error_type_text = item.error_type if item.error_type else "无"
        self.review_error_type_label.setText(f"错误类型：{error_type_text}")
        description_text = item.description if item.description else "无"
        self.review_description_label.setText(f"错误描述：{description_text}")
        self.review_origin.setPlainText(item.origin)
        self.review_suggestion.setPlainText(item.suggestion)
        self.review_edit.setPlainText("")

    def _use_suggestion(self) -> None:
        if not self.review_items:
            return
        item = self.review_items[self.review_index]
        self.review_edit.setPlainText(item.suggestion)

    def _apply_and_next(self) -> None:
        if not self.review_items:
            return
        item = self.review_items[self.review_index]
        new_text = self.review_edit.toPlainText().strip()
        if not new_text:
            self._skip_item()
            return

        md_path = self._resolve_md_path(item.filename)
        if not md_path:
            QtWidgets.QMessageBox.warning(self, "审查", "未找到文件")
            return

        if not replace_sentence_in_file(md_path, item.sentence, new_text):
            QtWidgets.QMessageBox.warning(
                self, "审查", "未找到对应句子，请手动更新"
            )
        else:
            self._log(f"已更新 {md_path}")

        self._advance_review()

    def _skip_item(self) -> None:
        if not self.review_items:
            return
        self._advance_review()

    def _advance_review(self) -> None:
        change_path = Path(self.review_change_field.text())
        out_path = Path(self.review_out_field.text())
        next_index = self.review_index + 1
        save_review_progress(change_path, out_path, next_index)
        if next_index >= len(self.review_items):
            clear_review_progress()

            # 成功结束后自动删除 changes.txt 和 changes_out.txt
            if change_path.name == "changes.txt" and out_path.name == "changes_out.txt":
                try:
                    change_path.unlink(missing_ok=True)
                    out_path.unlink(missing_ok=True)
                    self._log("已自动删除 changes.txt 和 changes_out.txt")
                except Exception as e:
                    self._log(f"⚠️ 自动删除失败: {e}")

            info = "审查完成"
            if self.failed_items:
                info += f"\n\n有 {len(self.failed_items)} 条待修改句子未在原文件中找到，请进入“运行”页查看日志并手动处理。"
                self._log("--- 未匹配句子汇总（请手动处理）---")
                for f in self.failed_items:
                    self._log(f"文件: {f.filename}")
                    self._log(f"标签: {f.label}")
                    self._log(f"原句: {f.sentence}")
                    self._log(f"建议: {f.suggestion}")
                    self._log("-" * 20)

            QtWidgets.QMessageBox.information(self, "审查", info)
            return
        self.review_list.setCurrentRow(next_index)

    def _resolve_md_path(self, filename: str) -> Optional[Path]:
        if filename in self.review_md_cache:
            return self.review_md_cache[filename]

        matches = [p for p in self.posts_dir.rglob(filename) if p.is_file()]
        if len(matches) == 1:
            self.review_md_cache[filename] = matches[0]
            return matches[0]
        if len(matches) > 1:
            items = [str(p) for p in matches]
            selection, ok = QtWidgets.QInputDialog.getItem(
                self, "选择文件", "发现多个匹配项", items, 0, False
            )
            if ok and selection:
                path = Path(selection)
                self.review_md_cache[filename] = path
                return path

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "定位 Markdown 文件", str(self.posts_dir), "Markdown (*.md)"
        )
        if path:
            resolved = Path(path)
            self.review_md_cache[filename] = resolved
            return resolved
        return None

    def _open_current_file(self) -> None:
        if not self.review_items:
            return
        item = self.review_items[self.review_index]
        path = self._resolve_md_path(item.filename)
        if not path:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _refresh_config_ui(self) -> None:
        self.config = load_config()
        self.posts_dir = get_posts_dir(self.config)
        self.host_field.setText(str(self.config.get("OLLAMA_HOST", "")))
        self.model_field.setText(str(self.config.get("OLLAMA_MODEL", "")))
        self.delay_spin.setValue(
            float(self.config.get("REQUEST_DELAY_SECONDS", 0.1)))
        self.temperature_field.setText(
            str(self.config.get("temperature", 1)))
        self.top_p_field.setText(
            str(self.config.get("top_p", 1)))
        self.posts_dir_edit.setText(str(self.posts_dir))
        self.prompt_field.setPlainText(str(self.config.get("SYSTEM_PROMPT", "")))
        self._update_run_mode()
        self._refresh_git_ui()

    def _reload_config_ui(self) -> None:
        self._refresh_config_ui()
        QtWidgets.QMessageBox.information(self, "配置", "配置已重新加载")

    def _save_config_ui(self) -> None:
        config = dict(self.config)
        host = self.host_field.text().strip()
        if host:
            config["OLLAMA_HOST"] = host
        else:
            config.pop("OLLAMA_HOST", None)
        config["OLLAMA_MODEL"] = self.model_field.text().strip()
        config["REQUEST_DELAY_SECONDS"] = float(self.delay_spin.value())
        try:
            config["temperature"] = float(self.temperature_field.text().strip())
        except ValueError:
            config["temperature"] = 1
        try:
            config["top_p"] = float(self.top_p_field.text().strip())
        except ValueError:
            config["top_p"] = 1
        posts_dir = self.posts_dir_edit.text().strip()
        if posts_dir:
            config["POSTS_DIR"] = posts_dir
        config["SYSTEM_PROMPT"] = self.prompt_field.toPlainText()
        save_config(config)
        self._log("配置已保存")
        self._refresh_config_ui()
        QtWidgets.QMessageBox.information(self, "配置", "配置已保存")

    def _refresh_git_ui(self) -> None:
        self.git_repo_label.setText(f"仓库：{self.posts_dir}")
        output = []
        diff_output = []

        if not (self.posts_dir / ".git").exists():
            output.append("不是 Git 仓库")
            self.git_output.setPlainText("\n".join(output))
            self.git_diff_view.setPlainText("")
            return

        status = self._run_git(["status", "--porcelain"], capture_output=True)
        if status.returncode == 0:
            if status.stdout.strip():
                output.append("检测到未提交的变更")
                output.append(status.stdout.strip())
            else:
                output.append("工作区干净")
        else:
            output.append("获取 Git 状态失败")
            if status.stderr:
                output.append(status.stderr.strip())

        diff_stat = self._run_git(["diff", "--stat"], capture_output=True)
        if diff_stat.returncode == 0 and diff_stat.stdout:
            output.append("\n变更摘要：")
            output.append(diff_stat.stdout.strip())

        self.git_output.setPlainText("\n".join(output))

        # 填充完整差异
        staged_diff = self._run_git(["diff", "--cached"], capture_output=True)
        if staged_diff.returncode == 0 and staged_diff.stdout.strip():
            diff_output.append("=== 已暂存的变更 (Staged) ===")
            diff_output.append(staged_diff.stdout.strip())

        unstaged_diff = self._run_git(["diff"], capture_output=True)
        if unstaged_diff.returncode == 0 and unstaged_diff.stdout.strip():
            if diff_output:
                diff_output.append("\n")
            diff_output.append("=== 未暂存的变更 (Unstaged) ===")
            diff_output.append(unstaged_diff.stdout.strip())

        if not diff_output:
            self.git_diff_view.setPlainText("无差异内容")
        else:
            self.git_diff_view.setPlainText("\n".join(diff_output))

    def _git_init_repo(self) -> None:
        if (self.posts_dir / ".git").exists():
            QtWidgets.QMessageBox.information(self, "Git", "仓库已初始化")
            return
        result = self._run_git(["init"], capture_output=True)
        if result.returncode == 0:
            self._refresh_git_ui()
            QtWidgets.QMessageBox.information(self, "Git", "仓库已初始化")
        else:
            QtWidgets.QMessageBox.warning(
                self, "Git", result.stderr or "初始化失败")

    def _git_stage_all(self) -> None:
        result = self._run_git(["add", "."], capture_output=True)
        if result.returncode == 0:
            self._refresh_git_ui()
            QtWidgets.QMessageBox.information(self, "Git", "已暂存全部变更")
        else:
            QtWidgets.QMessageBox.warning(self, "Git", result.stderr or "暂存失败")

    def _git_commit(self) -> None:
        message = self.git_message_field.text().strip()
        if not message:
            message = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            message = f"Auto-commit on {message}"
        result = self._run_git(["commit", "-m", message], capture_output=True)
        if result.returncode == 0:
            self._refresh_git_ui()
            QtWidgets.QMessageBox.information(self, "Git", f"已提交：{message}")
        else:
            QtWidgets.QMessageBox.warning(self, "Git", result.stderr or "提交失败")

    def _run_git(self, args: List[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(self.posts_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
        )


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont("Noto Sans CJK", 10)
    if not font.exactMatch():
        font = QtGui.QFont("Microsoft YaHei", 10)
    app.setFont(font)

    theme_manager = ThemeManager(app)
    theme_manager.enable_system_tracking()
    theme_manager.apply()

    window = MainWindow(theme_manager)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
