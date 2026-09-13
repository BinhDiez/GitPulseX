
#!/usr/bin/env python3
"""
GitHub Multi-Repository Release & Stats Collector

Sammelt Statistiken über ALLE Repositories eines GitHub-Benutzers.

Der Bericht enthält:
1. Gesamtübersicht (alle Repos zusammengefasst)
2. Pro Repository:
   - Release-Details mit Downloads/Tag
   - Plattform-Verteilung
   - Top Assets
   - Seitenaufrufe (nur mit Token)
   - Clone-Statistiken (nur mit Token)
   - Traffic-Quellen (nur mit Token)
   - Repository-Metriken (Stars, Forks, etc.)
   - Contributors
"""
import requests
from datetime import datetime, timezone
from pathlib import Path
import json
import argparse
import sys
import re
import os
from typing import Dict, List, Optional, Tuple

# PyQt5 Importe
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDateEdit, QComboBox, QTextEdit, QScrollArea,
    QWidget, QFrame, QMainWindow, QMessageBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QDate, pyqtSignal, QUrl, QRect, QSize, QMetaObject,
    Q_ARG, QEvent
)
from PyQt5.QtGui import (
    QPalette, QColor, QPixmap, QFontMetrics, QDesktopServices, QIcon
)

# ============================================================
# Konfiguration
# ============================================================
DEFAULT_OWNER = "BinhDiez"
DEFAULT_OUTPUT_FILE = "GitHub_all_repos_stats.txt"
DEFAULT_CONFIG_FILE = "github_stats_config.json"

# ============================================================
# Language-Klasse (für den Dialog)
# ============================================================
class Language:
    """Einfache Sprachverwaltung für den Dialog"""
    def __init__(self):
        self.current_lang = "de"
        self.translations = {
            "de": {
                "btn_ok": "OK",
                "btn_cancel": "Abbrechen",
                "app_title_format": "{}",
            }
        }

    def tr(self, key, *args):
        translations = self.translations.get(self.current_lang, {})
        text = translations.get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text

# ============================================================
# Dialog-Klasse (unverändert)
# ============================================================
class myUniversalDialog(QDialog):
    """Eigene MessageBox mit Logo, App-Icon, gestylten Buttons und Sprachausgabe"""

    closed = pyqtSignal()

    ACCEPT_ACTIONS = {
        'yes', 'ok', 'accept', 'no',
        'open', 'openfile', 'openfolder',
        'print', 'save', 'continue', 'clean',
        'retry', 'apply', 'install',
        'exit', 'restart'
    }

    REJECT_ACTIONS = {
        'cancel', 'close', 'abort', 'reject'
    }

    def __init__(self, parent=None, title="", message="", buttons=None,
                 icon_type="", voice_message="", default_button="",
                 text_alignment=Qt.AlignCenter, input_fields=None,
                 selectable_text=False, show_copy_button=False):
        if parent is Ellipsis:
            parent = None

        super().__init__(parent)

        if parent and hasattr(parent, 'lang'):
            self.lang = parent.lang
        else:
            self.lang = Language()

        self.parent_widget = parent
        self.message = message
        self.voice_message = voice_message or message
        self.buttons = buttons or [(self.lang.tr('btn_ok'), "primary", "accept")]
        self.icon_type = icon_type
        self.result_value = None
        self.default_button = default_button
        self.text_alignment = text_alignment
        self.button_widgets = []
        self.input_fields = input_fields or []
        self.input_widgets = {}
        self.input_values = {}
        self.selectable_text = selectable_text
        self.show_copy_button = show_copy_button
        self.msg_label = None
        self.msg_edit = None

        if parent and hasattr(parent, 'main_window'):
            self.main_window = parent.main_window
        else:
            self.main_window = self._find_main_window(parent)

        self.voice_enabled = self._get_voice_enabled()

        self.init_button_style()
        self.init_ui(title, message, buttons, icon_type)
        self._apply_ultimate_dark_mode()

        if hasattr(self, 'default_button_widget') and self.default_button_widget:
            QTimer.singleShot(50, self.default_button_widget.setFocus)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

    def init_ui(self, title, message, buttons, icon_type):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        max_dialog_height = int(screen_geometry.height() * 0.8)
        max_dialog_width = int(screen_geometry.width() * 0.7)

        self.setWindowTitle(self.lang.tr('app_title_format', title))
        self.setMinimumSize(800, 450)
        self.setMaximumSize(max_dialog_width, max_dialog_height)
        self.setSizeGripEnabled(True)
        self.setFocusPolicy(Qt.StrongFocus)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 15)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 5, 20, 5)
        header_layout.setSpacing(15)

        title_label = QLabel(f"{title}")
        title_label.setStyleSheet("""
            QLabel {
                color: #E0E0E0;
                font-size: 22px;
                font-weight: bold;
                padding: 5px;
            }
            """)
        header_layout.addWidget(title_label, 1, Qt.AlignCenter)
        main_layout.addWidget(header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(400)
        scroll_area.setMaximumHeight(600)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical { background: #3D3D3D; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #888888; }
        """)

        msg_container = QWidget()
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(20, 5, 20, 5)

        if icon_type and icon_type != "":
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            icon_texts = {
                "warning": "⚠️", "error": "❌", "question": "❓",
                "info": "ℹ️", "success": "✅"
            }
            icon_colors = {
                "warning": "#FF9800", "error": "#F44336", "question": "#2196F3",
                "info": "#2196F3", "success": "#4CAF50"
            }
            icon_label.setText(icon_texts.get(icon_type, "ℹ️"))
            icon_label.setStyleSheet(f"""
                font-size: 48px;
                background-color: transparent;
                color: {icon_colors.get(icon_type, "#E0E0E0")};
            """)
            msg_layout.addWidget(icon_label)

        if self.selectable_text or self.show_copy_button:
            msg_container_widget = QWidget()
            msg_container_layout = QVBoxLayout(msg_container_widget)
            msg_container_layout.setContentsMargins(0, 0, 0, 0)
            msg_container_layout.setSpacing(5)

            if self.selectable_text:
                self.msg_edit = QTextEdit()
                if "<a " in message:
                    fixed_message = self._fix_html_links(message)
                    self.msg_edit.setHtml(fixed_message)
                else:
                    self.msg_edit.setPlainText(message)
                self.msg_edit.setReadOnly(True)
                self.msg_edit.setObjectName("messageEdit")
                self.msg_edit.setFrameStyle(QFrame.NoFrame)
                self.msg_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.msg_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.msg_edit.setMinimumHeight(100)
                self.msg_edit.setStyleSheet("""
                    QTextEdit#messageEdit {
                        background-color: #3D3D3D;
                        color: #E0E0E0;
                        border: 1px solid #555555;
                        border-radius: 4px;
                        padding: 10px;
                        font-size: 14px;
                        font-family: 'Consolas', 'Courier New', monospace;
                    }
                """)
                msg_container_layout.addWidget(self.msg_edit)
            else:
                if "<a " in message:
                    fixed_message = self._fix_html_links(message)
                else:
                    fixed_message = message
                self.msg_label = QLabel(fixed_message)
                self.msg_label.setWordWrap(True)
                self.msg_label.setObjectName("messageLabel")
                self.msg_label.setStyleSheet("""
                    QLabel#messageLabel {
                        font-size: 16px;
                        padding: 15px;
                        color: #E0E0E0;
                        background-color: transparent;
                    }
                """)
                self.msg_label.setTextFormat(Qt.RichText)
                self.msg_label.setOpenExternalLinks(True)
                msg_container_layout.addWidget(self.msg_label)

            if self.show_copy_button:
                copy_btn = QPushButton("📋 Text kopieren")
                copy_btn.setObjectName("copyButton")
                copy_btn.setStyleSheet("""
                    QPushButton#copyButton {
                        background-color: #1565C0;
                        color: white;
                        border-radius: 4px;
                        padding: 5px 15px;
                        font-size: 12px;
                        max-width: 150px;
                    }
                    QPushButton#copyButton:hover { background-color: #0d47a1; }
                    QPushButton#copyButton:pressed { background-color: #0a3b8a; }
                """)
                copy_btn.clicked.connect(self._copy_text_to_clipboard)
                button_layout = QHBoxLayout()
                button_layout.addStretch()
                button_layout.addWidget(copy_btn)
                msg_container_layout.addLayout(button_layout)

            msg_layout.addWidget(msg_container_widget)
        else:
            if "<a " in message:
                fixed_message = self._fix_html_links(message)
            else:
                fixed_message = message
            self.msg_label = QLabel(fixed_message)
            self.msg_label.setWordWrap(True)
            self.msg_label.setObjectName("messageLabel")
            self.msg_label.setStyleSheet("""
                QLabel#messageLabel {
                    font-size: 16px;
                    padding: 15px;
                    color: #E0E0E0;
                    background-color: transparent;
                }
            """)
            self.msg_label.setTextFormat(Qt.RichText)
            self.msg_label.setOpenExternalLinks(True)
            if self.text_alignment == Qt.AlignLeft:
                self.msg_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.msg_label.setIndent(5)
            else:
                self.msg_label.setAlignment(Qt.AlignCenter)
            msg_layout.addWidget(self.msg_label)

        if self.input_fields:
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet("background-color: #555555; margin: 10px 0px;")
            msg_layout.addWidget(separator)
            for field_config in self.input_fields:
                field_widget = self._create_input_field(field_config)
                msg_layout.addWidget(field_widget)

        scroll_area.setWidget(msg_container)
        main_layout.addWidget(scroll_area)

        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setSpacing(15)
        button_layout.setContentsMargins(10, 10, 10, 10)

        self.default_button_widget = None
        self.button_widgets = []

        button_defs = buttons if buttons is not None else self.buttons
        max_button_width = 0
        for button_def in button_defs:
            if len(button_def) >= 3:
                text = button_def[0]
                temp_btn = QPushButton(text)
                font = temp_btn.font()
                metrics = QFontMetrics(font)
                text_width = metrics.horizontalAdvance(text)
                padding = 50
                width = text_width + padding
                max_button_width = max(max_button_width, width)
        max_button_width = min(max_button_width, 400)
        max_button_width = max(max_button_width, 100)

        for i, button_def in enumerate(button_defs):
            if len(button_def) == 3:
                text, style_type, action = button_def
            elif len(button_def) == 4:
                text, style_type, action, min_width = button_def
            else:
                continue

            btn = QPushButton(text)
            btn.setProperty("action", action)
            self.button_widgets.append(btn)

            is_default = (self.default_button == action or (i == 0 and not self.default_button))
            self.style_button(btn, style_type, (max_button_width, 40), is_default)
            btn.clicked.connect(lambda checked, r=action: self.handle_button(r))
            btn.setFocusPolicy(Qt.StrongFocus)
            button_layout.addWidget(btn)

            if is_default:
                self.default_button_widget = btn

        button_layout.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(button_widget)
        self.setLayout(main_layout)
        self.adjustSize()

    def init_button_style(self):
        self.button_styles = {
            'primary': {'bg': "#1565C0", 'hover': "#0d47a1"},
            'success': {'bg': "#2E7D32", 'hover': "#1B5E20"},
            'danger': {'bg': "#C62828", 'hover': "#8E0000"},
            'warning': {'bg': "#FF8a65", 'hover': "#F57C00"},
            'dark': {'bg': "#4a4a4a", 'hover': "#333333"}
        }

    def style_button(self, button, style_type, custom_size=None, is_default=False, min_width=None):
        style = self.button_styles.get(style_type, self.button_styles['primary'])
        focus_border = "3px solid #FFFFFF"
        focus_padding = "3px" if is_default else "1px"

        style_sheet = f"""
        QPushButton {{
            font-weight: bold;
            color: white;
            background-color: {style['bg']};
            border-radius: 10px;
            padding: 8px 16px;
            min-height: 20px;
            border: none;
            margin: 3px;
            font-size: 14px;
        }}
        QPushButton:hover {{ background-color: {style['hover']}; }}
        QPushButton:focus {{
            border: {focus_border};
            border-radius: 10px;
            background-color: {style['hover']};
            padding: {focus_padding};
        }}
        QPushButton:pressed {{
            background-color: {style['hover']};
            padding-top: 9px;
            padding-left: 9px;
        }}
        """
        button.setStyleSheet(style_sheet)
        if custom_size:
            button.setFixedWidth(custom_size[0])
            button.setFixedHeight(custom_size[1])
        else:
            font = button.font()
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(button.text())
            padding = 60
            width = max(100, min(text_width + padding, 500))
            button.setFixedWidth(width)
            button.setFixedHeight(40)

    def _create_input_field(self, field_config):
        field_type = field_config.get('type', 'text')
        label_text = field_config.get('label', '')
        field_name = field_config.get('name', f"field_{len(self.input_widgets)}")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 5, 10, 5)

        if label_text:
            label = QLabel(label_text)
            label.setStyleSheet("font-weight: bold; margin-top: 5px; font-size: 16px; color: #E0E0E0;")
            layout.addWidget(label)

        if field_type == 'text':
            widget = QLineEdit()
            widget.setText(str(field_config.get('default', '')))
            placeholder = field_config.get('placeholder', '')
            if placeholder:
                widget.setPlaceholderText(placeholder)
            layout.addWidget(widget)
        elif field_type == 'number':
            widget = QSpinBox()
            widget.setMinimum(field_config.get('min', -999999))
            widget.setMaximum(field_config.get('max', 999999))
            widget.setValue(int(field_config.get('default', 0)))
            layout.addWidget(widget)
        elif field_type == 'date':
            widget = QDateEdit()
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd.MM.yyyy")
            default = field_config.get('default', QDate.currentDate())
            if isinstance(default, str):
                default = QDate.fromString(default, "dd.MM.yyyy")
            widget.setDate(default)
            layout.addWidget(widget)
        elif field_type == 'combobox':
            widget = QComboBox()
            items = field_config.get('items', [])
            widget.addItems(items)
            default = field_config.get('default', None)
            if default is not None and default in items:
                widget.setCurrentText(default)
            elif items:
                widget.setCurrentIndex(0)
            layout.addWidget(widget)

        self.input_widgets[field_name] = widget
        return container

    def _apply_ultimate_dark_mode(self):
        self._force_dark_palette()
        self._apply_high_priority_stylesheet()
        self._apply_dark_theme_recursive(self)
        self._ensure_critical_widgets_visible()
        self.setAttribute(Qt.WA_StyledBackground, True)

    def _force_dark_palette(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.WindowText, QColor(224, 224, 224))
        dark_palette.setColor(QPalette.Base, QColor(61, 61, 61))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ToolTipText, QColor(224, 224, 224))
        dark_palette.setColor(QPalette.Text, QColor(224, 224, 224))
        dark_palette.setColor(QPalette.Button, QColor(61, 61, 61))
        dark_palette.setColor(QPalette.ButtonText, QColor(224, 224, 224))
        dark_palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.LinkVisited, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(dark_palette)

    def _apply_high_priority_stylesheet(self):
        self.setStyleSheet("""
            QDialog, QDialog * { background-color: #2D2D2D; color: #E0E0E0; }
            QLabel, QLabel * { color: #E0E0E0 !important; background-color: transparent; font-size: 16px; }
            QLineEdit, QSpinBox, QDateEdit, QComboBox {
                background-color: #3D3D3D; color: #E0E0E0 !important;
                border: 1px solid #555555; border-radius: 4px; padding: 5px;
                selection-background-color: #1565C0; selection-color: #FFFFFF; font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {
                border: 2px solid #1565C0;
            }
            QComboBox QAbstractItemView {
                background-color: #3D3D3D; color: #E0E0E0 !important;
                selection-background-color: #1565C0; selection-color: #FFFFFF;
            }
            QTextEdit {
                background-color: #3D3D3D; color: #E0E0E0 !important;
                border: 1px solid #555555; border-radius: 4px; padding: 5px; font-size: 14px;
            }
            QScrollArea, QScrollArea * { background-color: transparent; }
            QScrollBar:vertical { background: #3D3D3D; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background: #666666; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #888888; }
            QFrame, QFrame * { background-color: transparent; }
            * { color: #E0E0E0; }
        """)

    def _apply_dark_theme_recursive(self, widget):
        for child in widget.findChildren(QWidget):
            child.setPalette(self.palette())
            self._apply_dark_theme_recursive(child)

    def _ensure_critical_widgets_visible(self):
        for widget in self.input_widgets.values():
            if isinstance(widget, (QLineEdit, QSpinBox, QDateEdit, QComboBox)):
                widget.setStyleSheet(widget.styleSheet() + """
                    QLineEdit, QSpinBox, QDateEdit, QComboBox {
                        color: #E0E0E0 !important;
                        background-color: #3D3D3D;
                        font-size: 16px;
                    }
                """)
        for button in self.button_widgets:
            button.setStyleSheet(button.styleSheet() + " QPushButton { color: #FFFFFF !important; }")

    def _copy_text_to_clipboard(self):
        text_to_copy = self.message
        if self.msg_edit is not None:
            text_to_copy = self.msg_edit.toPlainText()
        elif self.msg_label is not None:
            text_to_copy = self.msg_label.text()
        clipboard = QApplication.clipboard()
        clipboard.setText(text_to_copy)

    def _fix_html_links(self, html_text):
        if not html_text or not ("<a " in html_text):
            return html_text

        def fix_link(match):
            full_tag = match.group(0)
            if 'href=' in full_tag:
                full_tag = re.sub(r'style="[^"]*"', '', full_tag)
                full_tag = full_tag.replace('>', ' style="color:#4FC3F7; text-decoration:underline;">')
                return full_tag
            else:
                content_match = re.search(r'<a[^>]*>(.*?)</a>', full_tag, re.DOTALL)
                if content_match:
                    link_text = content_match.group(1).strip()
                    if link_text and ('http' in link_text or 'www' in link_text):
                        return f'<a href="{link_text}" style="color:#4FC3F7; text-decoration:underline;">{link_text}</a>'
                return full_tag

        pattern = r'<a[^>]*>(.*?)</a>'
        return re.sub(pattern, fix_link, html_text, flags=re.DOTALL)

    def _handle_link_click(self, link):
        if link and link.toString():
            url = link.toString()
            if url.startswith("http") or url.startswith("https"):
                QDesktopServices.openUrl(QUrl(url))
            elif url.startswith("file:"):
                QDesktopServices.openUrl(QUrl(url))

    def _find_main_window(self, widget):
        if widget is None:
            return None
        current = widget
        while current is not None:
            if isinstance(current, QMainWindow) and hasattr(current, 'voice_enabled'):
                return current
            if hasattr(current, 'voice_enabled') and hasattr(current, 'page_changed'):
                return current
            try:
                parent = current.parent()
                if parent == current:
                    break
                current = parent
            except:
                break
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if isinstance(widget, QMainWindow) and hasattr(widget, 'voice_enabled'):
                    return widget
        return None

    def _get_voice_enabled(self):
        if self.main_window and hasattr(self.main_window, 'voice_enabled'):
            return self.main_window.voice_enabled
        return False

    def handle_button(self, action):
        if action in self.ACCEPT_ACTIONS and self.input_fields:
            collected_values = {}
            for name, widget in self.input_widgets.items():
                if isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QDateEdit):
                    value = widget.date().toString("dd.MM.yyyy")
                elif isinstance(widget, QComboBox):
                    value = widget.currentText()
                else:
                    value = None
                collected_values[name] = value
            self.input_values = collected_values

        self.result_value = action
        if action in self.REJECT_ACTIONS:
            self.reject()
        elif action in self.ACCEPT_ACTIONS:
            self.accept()
        else:
            self.accept()

    def get_input_values(self):
        return self.input_values

    def get_input_value(self, field_name):
        return self.input_values.get(field_name)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjust_dialog_height()
        if self.input_fields:
            QTimer.singleShot(100, self._select_all_text_in_first_input)

    def _select_all_text_in_first_input(self):
        if self.input_widgets:
            first_widget = list(self.input_widgets.values())[0]
            if isinstance(first_widget, QLineEdit):
                first_widget.setFocus()
                first_widget.selectAll()
            elif isinstance(first_widget, QSpinBox):
                first_widget.setFocus()
                first_widget.selectAll()
            elif isinstance(first_widget, QDateEdit):
                first_widget.setFocus()
                first_widget.lineEdit().selectAll()

    def exec_(self):
        result = super().exec_()
        if result == QDialog.Accepted and self.result_value in self.REJECT_ACTIONS:
            return QDialog.Rejected
        return result

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            self.closed.emit()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            current_focused = self.focusWidget()
            if isinstance(current_focused, (QLineEdit, QSpinBox, QDateEdit)):
                if len(self.input_widgets) > 1:
                    input_widgets_list = list(self.input_widgets.values())
                    if current_focused in input_widgets_list:
                        current_index = input_widgets_list.index(current_focused)
                        if current_index == len(input_widgets_list) - 1:
                            if self.default_button_widget:
                                self.default_button_widget.click()
                            elif self.button_widgets:
                                self.button_widgets[0].click()
                        else:
                            next_widget = input_widgets_list[current_index + 1]
                            next_widget.setFocus()
                else:
                    if self.default_button_widget:
                        self.default_button_widget.click()
                    elif self.button_widgets:
                        self.button_widgets[0].click()
            elif current_focused in self.button_widgets:
                current_focused.click()
            elif self.default_button_widget:
                self.default_button_widget.click()
            elif self.button_widgets:
                self.button_widgets[0].click()
        else:
            super().keyPressEvent(event)

    def adjust_dialog_height(self):
        temp_label = QLabel(self.message)
        temp_label.setWordWrap(True)
        temp_label.setTextFormat(Qt.RichText)
        available_width = self.width() - 80
        temp_label.resize(available_width, 10000)
        text_height = temp_label.heightForWidth(available_width)
        temp_label.deleteLater()
        base_height = 250
        icon_height = 50 if self.icon_type and self.icon_type != "" else 0
        total_height = base_height + text_height + icon_height + 60
        screen = QApplication.primaryScreen().availableGeometry()
        max_height = int(screen.height() * 0.8)
        self.setFixedHeight(min(int(total_height), max_height))

    def reject(self):
        if self.result_value is None:
            self.result_value = 'cancel'
        super().reject()
        self.closed.emit()

# ============================================================
# Konfigurationsmanagement (ERWEITERT)
# ============================================================
class Config:
    """Verwaltet Konfiguration aus Datei und Befehlszeile"""

    def __init__(self):
        self.owner = DEFAULT_OWNER
        self.token = ""
        self.output_file = DEFAULT_OUTPUT_FILE
        self.include_page_views = True
        self.include_traffic = True
        self.include_clones = True
        self.include_contributors = True
        self.include_forks = True
        self.include_stars = True
        self.include_watchers = True
        self.verbose = False
        self.show_dialog = True
        # NEU: Filter-Optionen
        self.skip_forks = True       # Geforkte Repos überspringen
        self.skip_archived = True    # Archivierte Repos überspringen
        self.skip_private = False    # Private Repos überspringen
        self.only_with_releases = False  # Nur Repos mit Releases
        self.repo_filter = ""        # Regex-Filter für Repo-Namen
        self.include_followers = True      # Follower-Liste abrufen
        self.followers_detail = True       # Details pro Follower (langsamer!)

    def load_from_file(self, config_file: str = DEFAULT_CONFIG_FILE):
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
                if self.verbose:
                    print(f"Konfiguration geladen von: {config_file}")
            except Exception as e:
                print(f"Warnung: Konfigurationsdatei konnte nicht geladen werden: {e}")

    def parse_args(self):
        parser = argparse.ArgumentParser(
            description="Sammelt GitHub Statistiken für ALLE Repositories eines Benutzers"
        )
        parser.add_argument("-o", "--owner", default=self.owner,
                            help=f"GitHub Benutzername (default: {self.owner})")
        parser.add_argument("-t", "--token", default=self.token,
                            help="GitHub Personal Access Token")
        parser.add_argument("-f", "--output", default=self.output_file,
                            help=f"Output Datei (default: {self.output_file})")
        parser.add_argument("--no-page-views", action="store_false",
                            dest="include_page_views", help="Seitenaufrufe nicht abfragen")
        parser.add_argument("--no-traffic", action="store_false",
                            dest="include_traffic", help="Traffic-Daten nicht abfragen")
        parser.add_argument("--no-clones", action="store_false",
                            dest="include_clones", help="Clone-Daten nicht abfragen")
        parser.add_argument("--no-dialog", action="store_false",
                            dest="show_dialog", help="Keinen Dialog anzeigen (nur Datei)")
        parser.add_argument("--include-forks", action="store_false",
                            dest="skip_forks", help="Geforkte Repos einschließen")
        parser.add_argument("--include-archived", action="store_false",
                            dest="skip_archived", help="Archivierte Repos einschließen")
        parser.add_argument("--include-private", action="store_true",
                            dest="skip_private", help="Private Repos einschließen")
        parser.add_argument("--only-with-releases", action="store_true",
                            dest="only_with_releases",
                            help="Nur Repos mit Releases anzeigen")
        parser.add_argument("--filter", default=self.repo_filter,
                            dest="repo_filter",
                            help="Regex-Filter für Repo-Namen")
        parser.add_argument("-v", "--verbose", action="store_true",
                            help="Ausführliche Ausgabe")

        parser.add_argument("--no-followers", action="store_false",
                            dest="include_followers", help="Follower nicht abfragen")
        parser.add_argument("--no-followers-detail", action="store_false",
                            dest="followers_detail",
                            help="Keine Detail-Abfrage pro Follower (schneller)")

        args = parser.parse_args()

        self.owner = args.owner
        self.token = args.token
        self.output_file = args.output
        self.include_page_views = args.include_page_views
        self.include_traffic = args.include_traffic
        self.include_clones = args.include_clones
        self.verbose = args.verbose
        self.show_dialog = args.show_dialog
        self.skip_forks = args.skip_forks
        self.skip_archived = args.skip_archived
        self.skip_private = args.skip_private
        self.only_with_releases = args.only_with_releases
        self.repo_filter = args.repo_filter
        self.include_followers = args.include_followers
        self.followers_detail = args.followers_detail


# ============================================================
# GitHub API Client (ERWEITERT um Repo-Liste)
# ============================================================
class GitHubStatsCollector:
    """Sammelt Statistiken von der GitHub API für ein einzelnes Repository"""

    def __init__(self, config: Config, repo_name: str = None):
        self.config = config
        self.repo_name = repo_name or config.owner
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        if config.token:
            self.headers["Authorization"] = f"Bearer {config.token}"

        self.base_url = "https://api.github.com"
        self.repo_url = f"{self.base_url}/repos/{config.owner}/{self.repo_name}"

        # Statistik-Speicher
        self.releases = []
        self.total_downloads = 0
        self.platform_stats = {
            "windows": 0, "mac_intel": 0, "mac_arm": 0, "linux": 0, "other": 0
        }
        self.assets = []
        self.page_views = None
        self.traffic_data = None
        self.clone_data = None
        self.contributors = []
        self.stars = 0
        self.forks = 0
        self.watchers = 0
        self.repo_info = None
        self.error = None

    def fetch_all_pages(self, url: str) -> List[dict]:
        all_data = []
        current_url = url
        while current_url:
            try:
                response = requests.get(current_url, headers=self.headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    all_data.extend(data)
                elif isinstance(data, dict):
                    all_data.append(data)
                current_url = response.links.get("next", {}).get("url")
            except requests.exceptions.RequestException as e:
                if self.config.verbose:
                    print(f"  Fehler beim Abrufen von {current_url}: {e}")
                break
        return all_data

    def fetch_releases(self):
        url = f"{self.repo_url}/releases"
        self.releases = self.fetch_all_pages(url)

        for release in self.releases:
            for asset in release.get("assets", []):
                count = asset["download_count"]
                self.total_downloads += count
                name = asset["name"].lower()
                if "windows" in name or "win" in name:
                    self.platform_stats["windows"] += count
                elif "intel" in name:
                    self.platform_stats["mac_intel"] += count
                elif any(x in name for x in ["apple", "arm", "silicon", "m1", "m2", "m3"]):
                    self.platform_stats["mac_arm"] += count
                elif "linux" in name:
                    self.platform_stats["linux"] += count
                else:
                    self.platform_stats["other"] += count
                self.assets.append((count, asset["name"]))
        self.assets.sort(reverse=True)

    def fetch_page_views(self):
        if not self.config.token:
            return
        try:
            url = f"{self.repo_url}/traffic/views"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.page_views = {
                    "count": data.get("count", 0),
                    "uniques": data.get("uniques", 0),
                    "views": data.get("views", [])
                }
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Seitenaufrufen für {self.repo_name}: {e}")

    def fetch_traffic(self):
        if not self.config.token or not self.config.include_traffic:
            return
        try:
            url = f"{self.repo_url}/traffic/popular/referrers"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                self.traffic_data = response.json()
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Traffic für {self.repo_name}: {e}")

    def fetch_clones(self):
        if not self.config.token or not self.config.include_clones:
            return
        try:
            url = f"{self.repo_url}/traffic/clones"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.clone_data = {
                    "count": data.get("count", 0),
                    "uniques": data.get("uniques", 0),
                    "clones": data.get("clones", [])
                }
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Clones für {self.repo_name}: {e}")

    def fetch_repository_metadata(self):
        try:
            response = requests.get(self.repo_url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.repo_info = data
                self.stars = data.get("stargazers_count", 0)
                self.forks = data.get("forks_count", 0)
                self.watchers = data.get("watchers_count", 0)

            if self.config.include_contributors:
                url = f"{self.repo_url}/contributors"
                self.contributors = self.fetch_all_pages(url)
        except Exception as e:
            if self.config.verbose:
                print(f"  Fehler bei Metadaten für {self.repo_name}: {e}")

    def collect_all(self):
        """Sammelt alle Statistiken für dieses Repo"""
        try:
            self.fetch_releases()
            self.fetch_repository_metadata()
            if self.config.include_page_views:
                self.fetch_page_views()
            if self.config.include_clones:
                self.fetch_clones()
            if self.config.include_traffic:
                self.fetch_traffic()
        except Exception as e:
            self.error = str(e)
            if self.config.verbose:
                print(f"❌ Fehler bei {self.repo_name}: {e}")

    @property
    def has_releases(self) -> bool:
        return len(self.releases) > 0

    @property
    def description(self) -> str:
        if self.repo_info:
            return self.repo_info.get("description", "") or ""
        return ""

    @property
    def language(self) -> str:
        if self.repo_info:
            return self.repo_info.get("language", "") or ""
        return ""

    @property
    def is_fork(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("fork", False)
        return False

    @property
    def is_archived(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("archived", False)
        return False

    @property
    def is_private(self) -> bool:
        if self.repo_info:
            return self.repo_info.get("private", False)
        return False

    @property
    def html_url(self) -> str:
        if self.repo_info:
            return self.repo_info.get("html_url", f"https://github.com/{self.config.owner}/{self.repo_name}")
        return f"https://github.com/{self.config.owner}/{self.repo_name}"

# ============================================================
# NEU: Multi-Repo Collector
# ============================================================
class MultiRepoCollector:
    """Sammelt Statistiken für ALLE Repositories eines Benutzers"""

    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-stats-collector"
        }
        if config.token:
            self.headers["Authorization"] = f"Bearer {config.token}"

        self.base_url = "https://api.github.com"
        self.repositories = []          # Liste der Repo-Namen
        self.collectors: Dict[str, GitHubStatsCollector] = {}
        self.repo_metadata: Dict[str, dict] = {}  # Rohe Repo-Infos

        self.followers = []              # Liste der Follower (Basis-Infos)
        self.followers_detailed = []     # Angereicherte Follower-Daten
        self.following_count = 0
        self.followers_count = 0
        self.user_info = None

    def fetch_user_repositories(self) -> List[dict]:
        """Holt alle Repositories eines Benutzers (paginiert)"""
        if self.config.verbose:
            print(f"🔍 Sammle Repository-Liste für Benutzer: {self.config.owner}...")

        all_repos = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/users/{self.config.owner}/repos"
            params = {
                "per_page": per_page,
                "page": page,
                "sort": "updated",
                "direction": "desc"
            }
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_repos.extend(data)
                if self.config.verbose:
                    print(f"  Seite {page}: {len(data)} Repos gefunden (gesamt: {len(all_repos)})")

                if len(data) < per_page:
                    break
                page += 1

            except requests.exceptions.RequestException as e:
                print(f"❌ Fehler beim Abrufen der Repo-Liste: {e}")
                break

        return all_repos

    def fetch_user_info(self):
        """Holt Basis-Infos des Benutzers (Follower-/Following-Counts)"""
        if self.config.verbose:
            print(f"👤 Sammle Benutzer-Info für: {self.config.owner}...")

        try:
            url = f"{self.base_url}/users/{self.config.owner}"
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                self.user_info = response.json()
                self.followers_count = self.user_info.get("followers", 0)
                self.following_count = self.user_info.get("following", 0)
                if self.config.verbose:
                    print(f"  Follower:  {self.followers_count:,}")
                    print(f"  Following: {self.following_count:,}")
        except Exception as e:
            print(f"❌ Fehler beim Abrufen der Benutzer-Info: {e}")

    def fetch_followers(self):
        """Holt alle Follower des Benutzers (paginiert)"""
        if not self.config.include_followers:
            return

        if self.config.verbose:
            print(f"👥 Sammle Follower-Liste für: {self.config.owner}...")

        all_followers = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/users/{self.config.owner}/followers"
            params = {"per_page": per_page, "page": page}
            try:
                response = requests.get(url, headers=self.headers,
                                        params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                all_followers.extend(data)
                if self.config.verbose:
                    print(f"  Seite {page}: {len(data)} Follower "
                        f"(gesamt: {len(all_followers)})")

                if len(data) < per_page:
                    break
                page += 1

            except requests.exceptions.RequestException as e:
                print(f"❌ Fehler beim Abrufen der Follower: {e}")
                break

        self.followers = all_followers
        if self.config.verbose:
            print(f"✅ {len(self.followers)} Follower gesammelt")

    def enrich_followers(self):
        """Reichert Follower mit Detail-Infos an (Location, Bio, Repos, etc.)"""
        if not self.config.followers_detail or not self.followers:
            return

        if self.config.verbose:
            print(f"🔎 Lade Details für {len(self.followers)} Follower...")

        detailed = []
        total = len(self.followers)

        for i, follower in enumerate(self.followers, 1):
            login = follower.get("login")
            if not login:
                continue

            try:
                url = f"{self.base_url}/users/{login}"
                response = requests.get(url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    detailed.append({
                        "login": data.get("login", login),
                        "name": data.get("name", "") or "",
                        "location": (data.get("location", "") or "").strip(),
                        "company": (data.get("company", "") or "").strip(),
                        "bio": (data.get("bio", "") or "").strip(),
                        "blog": (data.get("blog", "") or "").strip(),
                        "public_repos": data.get("public_repos", 0),
                        "followers": data.get("followers", 0),
                        "following": data.get("following", 0),
                        "created_at": data.get("created_at", ""),
                        "html_url": data.get("html_url", ""),
                    })

                # Rate-Limit-Schutz: kleine Pause alle 10 Requests
                if i % 10 == 0:
                    import time
                    time.sleep(0.5)

                if self.config.verbose and i % 50 == 0:
                    print(f"  {i}/{total} Follower angereichert...")

            except Exception as e:
                if self.config.verbose:
                    print(f"  ⚠️  Fehler bei {login}: {e}")

        self.followers_detailed = detailed
        if self.config.verbose:
            print(f"✅ {len(detailed)} Follower mit Details angereichert")

    def filter_repositories(self, repos: List[dict]) -> List[dict]:
        """Filtert Repositories nach den Konfigurationsoptionen"""
        filtered = []
        regex = None
        if self.config.repo_filter:
            try:
                regex = re.compile(self.config.repo_filter, re.IGNORECASE)
            except re.error as e:
                print(f"⚠️  Ungültiger Regex-Filter: {e}")

        for repo in repos:
            name = repo.get("name", "")

            if self.config.skip_forks and repo.get("fork", False):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe Fork: {name}")
                continue

            if self.config.skip_archived and repo.get("archived", False):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe archiviert: {name}")
                continue

            if self.config.skip_private and repo.get("private", False):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe privat: {name}")
                continue

            if regex and not regex.search(name):
                if self.config.verbose:
                    print(f"  ⏭️  Überspringe (Filter): {name}")
                continue

            filtered.append(repo)

        return filtered

    def collect_all(self):
        """Sammelt alle Repos und deren Statistiken"""
        # 0. Benutzer-Info und Follower zuerst
        self.fetch_user_info()
        self.fetch_followers()
        self.enrich_followers()

        # 1. Repo-Liste holen
        all_repos = self.fetch_user_repositories()

        if not all_repos:
            print("❌ Keine Repositories gefunden!")
            return

        # 2. Filtern
        filtered_repos = self.filter_repositories(all_repos)

        print(f"📦 {len(filtered_repos)} von {len(all_repos)} Repositories werden analysiert...")
        print("")

        # 3. Pro Repo Stats sammeln
        for i, repo in enumerate(filtered_repos, 1):
            repo_name = repo["name"]
            self.repo_metadata[repo_name] = repo

            if self.config.verbose:
                print(f"[{i}/{len(filtered_repos)}] Analysiere: {repo_name}")

            collector = GitHubStatsCollector(self.config, repo_name)
            collector.collect_all()

            # Nur Repos mit Releases behalten, wenn gewünscht
            if self.config.only_with_releases and not collector.has_releases:
                if self.config.verbose:
                    print(f"  ⏭️  Keine Releases, übersprungen")
                continue

            self.collectors[repo_name] = collector
            self.repositories.append(repo_name)

        if self.config.verbose:
            print("")
            print(f"✅ Analyse abgeschlossen: {len(self.collectors)} Repositories mit Daten")

    def get_total_stats(self) -> dict:
        """Berechnet Gesamtstatistiken über alle Repos"""
        total_downloads = 0
        total_stars = 0
        total_forks = 0
        total_watchers = 0
        total_releases = 0
        total_assets = 0
        total_views = 0
        total_unique_views = 0
        total_clones = 0
        total_unique_clones = 0
        platform_totals = {
            "windows": 0, "mac_intel": 0, "mac_arm": 0, "linux": 0, "other": 0
        }

        for collector in self.collectors.values():
            total_downloads += collector.total_downloads
            total_stars += collector.stars
            total_forks += collector.forks
            total_watchers += collector.watchers
            total_releases += len(collector.releases)
            total_assets += len(collector.assets)

            for key in platform_totals:
                platform_totals[key] += collector.platform_stats.get(key, 0)

            if collector.page_views:
                total_views += collector.page_views.get("count", 0)
                total_unique_views += collector.page_views.get("uniques", 0)

            if collector.clone_data:
                total_clones += collector.clone_data.get("count", 0)
                total_unique_clones += collector.clone_data.get("uniques", 0)

        return {
            "repos_analyzed": len(self.collectors),
            "total_downloads": total_downloads,
            "total_stars": total_stars,
            "total_forks": total_forks,
            "total_watchers": total_watchers,
            "total_releases": total_releases,
            "total_assets": total_assets,
            "total_views": total_views,
            "total_unique_views": total_unique_views,
            "total_clones": total_clones,
            "total_unique_clones": total_unique_clones,
            "platform_totals": platform_totals,
        }

# ============================================================
# NEU: Multi-Repo Report Generator
# ============================================================
class MultiRepoReportGenerator:
    """Erstellt einen übersichtlichen Bericht für alle Repositories"""

    def __init__(self, multi_collector: MultiRepoCollector):
        self.multi = multi_collector
        self.lines = []

    def add_line(self, line: str = ""):
        self.lines.append(line)

    def add_section(self, title: str, char: str = "=", width: int = 80):
        self.lines.append(char * width)
        self.lines.append(title)
        self.lines.append(char * width)
        self.lines.append("")

    def generate_report(self):
        """Generiert den vollständigen Bericht"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        config = self.multi.config

        # ===== HEADER =====
        self.add_section("📊 GitHub Multi-Repository Statistik")
        self.add_line(f"Benutzer:    {config.owner}")
        self.add_line(f"Erstellt:    {now}")
        self.add_line(f"Repos:       {len(self.multi.collectors)} analysiert")
        self.add_line("")

        # ===== NEU: FOLLOWER-ÜBERSICHT =====
        self._add_followers_overview()

        # ===== GESAMTÜBERSICHT =====
        self._add_overview()

        # ===== REPO-RANKING =====
        self._add_repo_ranking()

        # ===== DETAILS PRO REPO =====
        self.add_section("📋 DETAILS PRO REPOSITORY", "=")
        self.add_line("")

        # Sortiere Repos nach Downloads (absteigend)
        sorted_repos = sorted(
            self.multi.collectors.items(),
            key=lambda x: x[1].total_downloads,
            reverse=True
        )

        for i, (repo_name, collector) in enumerate(sorted_repos, 1):
            self._add_repo_details(repo_name, collector, i)

        # ===== FOOTER =====
        self.add_section("📈 Ende der Statistik")

    def _add_overview(self):
        """Fügt die Gesamtübersicht hinzu"""
        self.add_section("🌍 GESAMTÜBERSICHT", "-")

        stats = self.multi.get_total_stats()

        self.add_line(f"{'Metrik':<30} {'Wert':>15}")
        self.add_line("-" * 47)
        self.add_line(f"{'Analysierte Repositories':<30} {stats['repos_analyzed']:>15,}")
        self.add_line(f"{'Gesamt Downloads':<30} {stats['total_downloads']:>15,}")
        self.add_line(f"{'Gesamt Releases':<30} {stats['total_releases']:>15,}")
        self.add_line(f"{'Gesamt Assets':<30} {stats['total_assets']:>15,}")
        self.add_line(f"{'Gesamt Stars':<30} {stats['total_stars']:>15,}")
        self.add_line(f"{'Gesamt Forks':<30} {stats['total_forks']:>15,}")
        self.add_line(f"{'Gesamt Watchers':<30} {stats['total_watchers']:>15,}")

        if self.multi.config.include_page_views and stats['total_views'] > 0:
            self.add_line(f"{'Seitenaufrufe (14 Tage)':<30} {stats['total_views']:>15,}")
            self.add_line(f"{'Einzigartige Besucher':<30} {stats['total_unique_views']:>15,}")

        if self.multi.config.include_clones and stats['total_clones'] > 0:
            self.add_line(f"{'Clones (14 Tage)':<30} {stats['total_clones']:>15,}")
            self.add_line(f"{'Einzigartige Cloner':<30} {stats['total_unique_clones']:>15,}")

        self.add_line("")

        # Plattform-Verteilung gesamt
        platform = stats['platform_totals']
        total_platform = sum(platform.values())

        if total_platform > 0:
            self.add_line("💻 Plattform-Verteilung (Gesamt):")
            self.add_line(f"{'Plattform':<25} {'Downloads':>12} {'Anteil':>8}")
            self.add_line("-" * 47)

            labels = {
                "windows": "Windows",
                "mac_intel": "macOS Intel",
                "mac_arm": "macOS Apple Silicon",
                "linux": "Linux",
                "other": "Sonstige"
            }
            for key, label in labels.items():
                count = platform.get(key, 0)
                pct = (count / total_platform * 100) if total_platform > 0 else 0
                self.add_line(f"{label:<25} {count:>12,} {pct:>7.1f}%")

            self.add_line("")

    def _add_repo_ranking(self):
        """Fügt eine Rangliste aller Repos hinzu"""
        self.add_section("🏆 REPOSITORY-RANKING (nach Downloads)", "-")

        sorted_repos = sorted(
            self.multi.collectors.items(),
            key=lambda x: x[1].total_downloads,
            reverse=True
        )

        # Top-Liste
        self.add_line(f"{'#':<4} {'Repository':<30} {'Downloads':>12} {'Stars':>8} {'Releases':>9}")
        self.add_line("-" * 66)

        for i, (repo_name, collector) in enumerate(sorted_repos[:30], 1):
            self.add_line(
                f"{i:<4} {repo_name[:30]:<30} "
                f"{collector.total_downloads:>12,} "
                f"{collector.stars:>8,} "
                f"{len(collector.releases):>9}"
            )

        if len(sorted_repos) > 30:
            self.add_line(f"... und {len(sorted_repos) - 30} weitere Repositories")

        self.add_line("")

        # Sprach-Verteilung
        self._add_language_distribution()

    def _add_language_distribution(self):
        """Zeigt die Verteilung nach Programmiersprache"""
        languages = {}
        for repo_name, collector in self.multi.collectors.items():
            lang = collector.language or "Unbekannt"
            if lang not in languages:
                languages[lang] = {"count": 0, "downloads": 0, "stars": 0}
            languages[lang]["count"] += 1
            languages[lang]["downloads"] += collector.total_downloads
            languages[lang]["stars"] += collector.stars

        if not languages:
            return

        self.add_section("💻 SPRACH-VERTEILUNG", "-")
        self.add_line(f"{'Sprache':<20} {'Repos':>8} {'Downloads':>12} {'Stars':>8}")
        self.add_line("-" * 52)

        sorted_langs = sorted(
            languages.items(),
            key=lambda x: x[1]["downloads"],
            reverse=True
        )
        for lang, data in sorted_langs:
            self.add_line(
                f"{lang[:20]:<20} {data['count']:>8} "
                f"{data['downloads']:>12,} {data['stars']:>8,}"
            )
        self.add_line("")

    def _add_repo_details(self, repo_name: str, collector: GitHubStatsCollector, index: int):
        """Fügt die Details eines einzelnen Repositories hinzu"""
        # Trennzeile mit Repo-Namen
        separator = f"═══ [{index}] {repo_name} ═══"
        self.add_line(separator)
        self.add_line("")

        # Beschreibung
        if collector.description:
            self.add_line(f"📝 {collector.description[:100]}")
            self.add_line("")

        # Repository-Metadaten
        self.add_line(f"🔗 URL:        {collector.html_url}")
        if collector.language:
            self.add_line(f"💻 Sprache:    {collector.language}")
        self.add_line(f"⭐ Stars:      {collector.stars:,}")
        self.add_line(f"🍴 Forks:      {collector.forks:,}")
        self.add_line(f"👁️  Watchers:   {collector.watchers:,}")
        self.add_line(f"📦 Releases:   {len(collector.releases)}")
        self.add_line(f"📥 Downloads:  {collector.total_downloads:,}")
        self.add_line("")

        # Releases
        if collector.releases:
            self._add_repo_releases(collector)
        else:
            self.add_line("⚠️  Keine Releases vorhanden.")
            self.add_line("")

        # Plattform-Verteilung
        if collector.total_downloads > 0:
            self._add_repo_platforms(collector)

        # Top Assets
        if collector.assets:
            self._add_repo_top_assets(collector)

        # Traffic (nur mit Token)
        if collector.page_views:
            self._add_repo_page_views(collector)

        if collector.clone_data:
            self._add_repo_clones(collector)

        if collector.traffic_data:
            self._add_repo_traffic(collector)

        # Contributors
        if collector.contributors:
            self._add_repo_contributors(collector)

        self.add_line("")

    def _add_repo_releases(self, collector: GitHubStatsCollector):
        """Release-Details für ein Repo"""
        self.add_line("  📦 Release-Details:")
        now = datetime.now(timezone.utc)

        # Max 10 Releases detailliert
        for release in collector.releases[:10]:
            release_name = release.get("name") or release["tag_name"]
            tag_name = release["tag_name"]
            published = release.get("published_at", "")
            release_total = 0

            for asset in release.get("assets", []):
                release_total += asset["download_count"]

            # Alter berechnen
            try:
                release_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
                age_days = max((now - release_date).days, 1)
            except:
                age_days = 1

            dl_per_day = release_total / age_days
            date_short = published[:10] if published else "?"

            self.add_line(f"    • {release_name[:40]:<40} ({tag_name})")
            self.add_line(f"      Datum: {date_short}  |  Downloads: {release_total:,}  |  {dl_per_day:.2f}/Tag")

            # Top 3 Assets pro Release
            if release.get("assets"):
                top_assets = sorted(
                    release["assets"],
                    key=lambda a: a["download_count"],
                    reverse=True
                )[:3]
                for asset in top_assets:
                    self.add_line(
                        f"        - {asset['download_count']:>8,}  {asset['name']}"
                    )

        if len(collector.releases) > 10:
            self.add_line(f"    ... und {len(collector.releases) - 10} weitere Releases")

        self.add_line("")

    def _add_repo_platforms(self, collector: GitHubStatsCollector):
        """Plattform-Verteilung für ein Repo"""
        stats = collector.platform_stats
        total = sum(stats.values())

        if total == 0:
            return

        self.add_line("  💻 Plattform-Verteilung:")
        labels = {
            "windows": "Windows",
            "mac_intel": "macOS Intel",
            "mac_arm": "macOS ARM",
            "linux": "Linux",
            "other": "Sonstige"
        }
        for key, label in labels.items():
            count = stats.get(key, 0)
            if count > 0:
                pct = (count / total * 100)
                bar = "█" * int(pct / 5)
                self.add_line(f"    {label:<15} {count:>8,}  {pct:>5.1f}%  {bar}")
        self.add_line("")

    def _add_repo_top_assets(self, collector: GitHubStatsCollector):
        """Top Assets für ein Repo"""
        self.add_line("  🏆 Top Assets:")
        for count, name in collector.assets[:5]:
            self.add_line(f"    {count:>8,}  {name}")
        self.add_line("")

    def _add_repo_page_views(self, collector: GitHubStatsCollector):
        """Seitenaufrufe für ein Repo"""
        views = collector.page_views
        self.add_line(f"  👁️  Seitenaufrufe (14 Tage): {views['count']:,} "
                      f"(unique: {views['uniques']:,})")

        if views.get("views"):
            # Letzte 7 Tage als Mini-Tabelle
            recent = views["views"][-7:]
            self.add_line("    Letzte Tage:")
            for day in recent:
                date = day["timestamp"][:10]
                bar = "█" * min(day["count"] // 5, 40)
                self.add_line(f"      {date}  {day['count']:>5}  {bar}")
        self.add_line("")

    def _add_repo_clones(self, collector: GitHubStatsCollector):
        """Clone-Statistiken für ein Repo"""
        clones = collector.clone_data
        self.add_line(f"  📦 Clones (14 Tage): {clones['count']:,} "
                      f"(unique: {clones['uniques']:,})")
        self.add_line("")

    def _add_repo_traffic(self, collector: GitHubStatsCollector):
        """Traffic-Quellen für ein Repo"""
        if not collector.traffic_data:
            return
        self.add_line("  🔗 Top Referrer:")
        for ref in collector.traffic_data[:5]:
            name = ref["referrer"] or "Direkt"
            self.add_line(
                f"    {name[:35]:<35} {ref['count']:>6} views"
            )
        self.add_line("")

    def _add_repo_contributors(self, collector: GitHubStatsCollector):
        """Contributors für ein Repo"""
        self.add_line(f"  👥 Contributors ({len(collector.contributors)}):")
        for contrib in collector.contributors[:5]:
            name = contrib.get("login", "?")
            commits = contrib.get("contributions", 0)
            self.add_line(f"    {name[:30]:<30} {commits:>5} commits")
        if len(collector.contributors) > 5:
            self.add_line(f"    ... und {len(collector.contributors) - 5} weitere")
        self.add_line("")

    def get_report_text(self) -> str:
        return "\n".join(self.lines)

    def save(self, output_file: str) -> Path:
        outfile = Path(output_file)
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(self.get_report_text())
        return outfile

    def _add_followers_overview(self):
        """Fügt die Follower-Auswertung hinzu"""
        multi = self.multi
        config = multi.config

        if not config.include_followers:
            return

        self.add_section("👥 FOLLOWER-ANALYSE", "-")

        # Basis-Zahlen
        followers_count = multi.followers_count or len(multi.followers)
        following_count = multi.following_count

        # Follower/Following-Ratio
        ratio = (followers_count / following_count) if following_count > 0 else 0

        self.add_line(f"{'Metrik':<30} {'Wert':>15}")
        self.add_line("-" * 47)
        self.add_line(f"{'Follower':<30} {followers_count:>15,}")
        self.add_line(f"{'Following':<30} {following_count:>15,}")
        self.add_line(f"{'Follower/Following-Ratio':<30} {ratio:>15.2f}")
        self.add_line("")

        # Falls keine Details geladen wurden
        if not multi.followers_detailed:
            if multi.followers:
                self.add_line("Basis-Follower-Liste (ohne Detail-Infos):")
                for f in multi.followers[:20]:
                    self.add_line(f"  • {f.get('login', '?')}")
                if len(multi.followers) > 20:
                    self.add_line(f"  ... und {len(multi.followers) - 20} weitere")
                self.add_line("")
            return

        # ===== DETAIL-AUSWERTUNG =====
        detailed = multi.followers_detailed

        # 1. Geografische Verteilung (aus location-Freitext)
        self._add_followers_by_location(detailed)

        # 2. Top-Unternehmen
        self._add_followers_by_company(detailed)

        # 3. Einflussreichste Follower (nach eigenen Followern)
        self._add_top_followers(detailed)

        # 4. Altersverteilung der Accounts
        self._add_followers_by_account_age(detailed)

        # 5. Vollständige Liste (kompakt)
        self._add_followers_list(detailed)


    def _add_followers_by_location(self, detailed):
        """Gruppiert Follower nach Location (Freitext)"""
        self.add_line("🌍 Follower nach Ort (Freitext-Feld):")

        locations = {}
        without_location = 0

        for f in detailed:
            loc = f["location"]
            if not loc:
                without_location += 1
                continue
            # Normalisieren: Erster Teil vor Komma, Titel-Case
            normalized = loc.split(",")[0].strip().title()
            locations[normalized] = locations.get(normalized, 0) + 1

        if not locations:
            self.add_line("  Keine Ortsangaben vorhanden.")
            self.add_line("")
            return

        sorted_locs = sorted(locations.items(), key=lambda x: x[1], reverse=True)

        self.add_line(f"  {'Ort':<35} {'Anzahl':>8}")
        self.add_line("  " + "-" * 45)
        for loc, count in sorted_locs[:20]:
            bar = "█" * min(count, 30)
            self.add_line(f"  {loc[:35]:<35} {count:>8}  {bar}")

        if len(sorted_locs) > 20:
            self.add_line(f"  ... und {len(sorted_locs) - 20} weitere Orte")

        if without_location > 0:
            self.add_line(f"  (ohne Ortsangabe: {without_location})")
        self.add_line("")

        # Hinweis zur Datenqualität
        self.add_line("  ℹ️  Hinweis: location ist ein Freitext-Feld und "
                    "daher ungenau/nicht standardisiert.")
        self.add_line("")


    def _add_followers_by_company(self, detailed):
        """Gruppiert Follower nach Unternehmen"""
        companies = {}
        for f in detailed:
            comp = f["company"]
            if not comp:
                continue
            # Normalisieren: @ entfernen
            normalized = comp.lstrip("@").strip()
            companies[normalized] = companies.get(normalized, 0) + 1

        if not companies:
            return

        self.add_line("🏢 Top-Unternehmen/Organisationen:")
        sorted_companies = sorted(companies.items(),
                                key=lambda x: x[1], reverse=True)

        for comp, count in sorted_companies[:15]:
            self.add_line(f"  {comp[:40]:<40} {count:>5}")
        self.add_line("")


    def _add_top_followers(self, detailed):
        """Zeigt die einflussreichsten Follower (nach eigenen Followern)"""
        if not detailed:
            return

        self.add_line("⭐ Top-Follower (nach eigenen Followern):")
        self.add_line(f"  {'#':<4} {'Login':<25} {'Follower':>10} {'Repos':>7} {'Ort'}")
        self.add_line("  " + "-" * 75)

        sorted_followers = sorted(detailed,
                                key=lambda x: x["followers"],
                                reverse=True)

        for i, f in enumerate(sorted_followers[:20], 1):
            login = f["login"][:25]
            followers = f["followers"]
            repos = f["public_repos"]
            loc = f["location"][:25] if f["location"] else "—"
            self.add_line(
                f"  {i:<4} {login:<25} {followers:>10,} {repos:>7} {loc}"
            )
        self.add_line("")


    def _add_followers_by_account_age(self, detailed):
        """Verteilt Follower nach Account-Alter"""
        if not detailed:
            return

        now = datetime.now(timezone.utc)
        buckets = {
            "< 1 Jahr": 0,
            "1-3 Jahre": 0,
            "3-5 Jahre": 0,
            "5-10 Jahre": 0,
            "> 10 Jahre": 0,
            "Unbekannt": 0,
        }

        for f in detailed:
            created = f.get("created_at", "")
            if not created:
                buckets["Unbekannt"] += 1
                continue
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (now - created_dt).days
                age_years = age_days / 365.25

                if age_years < 1:
                    buckets["< 1 Jahr"] += 1
                elif age_years < 3:
                    buckets["1-3 Jahre"] += 1
                elif age_years < 5:
                    buckets["3-5 Jahre"] += 1
                elif age_years < 10:
                    buckets["5-10 Jahre"] += 1
                else:
                    buckets["> 10 Jahre"] += 1
            except:
                buckets["Unbekannt"] += 1

        total = sum(buckets.values())
        if total == 0:
            return

        self.add_line("📅 Follower nach Account-Alter:")
        for bucket, count in buckets.items():
            if count == 0:
                continue
            pct = (count / total * 100)
            bar = "█" * int(pct / 3)
            self.add_line(f"  {bucket:<15} {count:>5}  {pct:>5.1f}%  {bar}")
        self.add_line("")


    def _add_followers_list(self, detailed):
        """Kompakte Liste aller Follower mit Details"""
        if not detailed:
            return

        self.add_line(f"📋 Alle Follower ({len(detailed)}):")
        self.add_line(
            f"  {'Login':<25} {'Name':<25} {'Ort':<20} {'Followers':>9}"
        )
        self.add_line("  " + "-" * 82)

        for f in sorted(detailed, key=lambda x: x["login"].lower()):
            login = f["login"][:25]
            name = (f["name"] or "—")[:25]
            loc = (f["location"] or "—")[:20]
            followers = f["followers"]
            self.add_line(
                f"  {login:<25} {name:<25} {loc:<20} {followers:>9,}"
            )
        self.add_line("")

# ============================================================
# Hauptprogramm
# ============================================================
def main():
    """Hauptfunktion"""
    config = Config()
    config.load_from_file()
    config.parse_args()

    if config.verbose:
        print("🚀 Starte GitHub Multi-Repository Statistik Collector")
        print(f"👤 Benutzer:  {config.owner}")
        print(f"📄 Ausgabe:   {config.output_file}")
        print("")

    # Statistiken sammeln (ALLE Repos)
    multi_collector = MultiRepoCollector(config)
    multi_collector.collect_all()

    if not multi_collector.collectors:
        print("❌ Keine Daten zum Auswerten gefunden!")
        return 1

    # Bericht erstellen
    report = MultiRepoReportGenerator(multi_collector)
    report.generate_report()

    # Bericht speichern
    output_path = report.save(config.output_file)

    # Zusammenfassung in Konsole
    stats = multi_collector.get_total_stats()
    print("")
    print("📊 ZUSAMMENFASSUNG:")
    print(f"  Repositories:   {stats['repos_analyzed']}")
    print(f"  Downloads:      {stats['total_downloads']:,}")
    print(f"  Releases:       {stats['total_releases']}")
    print(f"  Assets:         {stats['total_assets']}")
    print(f"  Stars:          {stats['total_stars']:,}")
    print(f"  Forks:          {stats['total_forks']:,}")
    if stats['total_views']:
        print(f"  Seitenaufrufe:  {stats['total_views']:,}")
    if stats['total_clones']:
        print(f"  Clones:         {stats['total_clones']:,}")
    print(f"  Bericht:        {output_path}")

    # ===== DIALOG ANZEIGEN =====
    if config.show_dialog:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        report_text = report.get_report_text()
        report_text = re.sub(r'^=+$\s*', '', report_text, flags=re.MULTILINE)

        # Auf max. 100.000 Zeichen begrenzen für Dialog-Performance
        if len(report_text) > 100000:
            report_text = report_text[:100000] + "\n\n... (Bericht gekürzt, siehe Datei)"

        dialog = myUniversalDialog(
            None,
            "GitHub Multi-Repository Statistik",
            report_text,
            buttons=[("OK", "primary", "accept"),
                     ("In Datei öffnen", "success", "open")],
            icon_type="",
            selectable_text=True,
            show_copy_button=True,
            text_alignment=Qt.AlignLeft
        )

        def handle_dialog_result():
            if dialog.result_value == "open":
                import subprocess
                import platform
                try:
                    if platform.system() == "Windows":
                        os.startfile(str(output_path))
                    elif platform.system() == "Darwin":
                        subprocess.run(["open", str(output_path)])
                    else:
                        subprocess.run(["xdg-open", str(output_path)])
                except Exception as e:
                    print(f"Fehler beim Öffnen der Datei: {e}")
                    msg_box = QMessageBox()
                    msg_box.setWindowTitle("Fehler")
                    msg_box.setText(f"Datei konnte nicht geöffnet werden:\n{e}")
                    msg_box.setIcon(QMessageBox.Warning)
                    msg_box.exec_()

        dialog.finished.connect(handle_dialog_result)
        dialog.exec_()

    return 0


if __name__ == "__main__":
    sys.exit(main())
