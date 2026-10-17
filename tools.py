import json
import os
from collections.abc import Callable

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import QButtonGroup, QColorDialog, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

import settings
from resources import get_resource_path


class ToolPalette(QWidget):
    mode_changed = pyqtSignal(str)

    def __init__(self, is_editing_postit: Callable[[], bool]) -> None:
        super().__init__()
        self.is_editing_postit = is_editing_postit
        self.annotation_colors = dict(settings.ANNOTATION_COLORS)
        self.load_custom_colors()
        self.setFixedWidth(60)
        self.setStyleSheet("background-color: #252525; border-left: 1px solid #1a1a1a;")
        rt_layout = QVBoxLayout(self)
        rt_layout.setContentsMargins(5, 15, 5, 15)
        rt_layout.setSpacing(15)

        tool_css = """
            QPushButton { border: none; border-radius: 6px; padding: 8px; }
            QPushButton:checked { background-color: #3a3a3a; }
            QPushButton:hover { background-color: #444444; }
        """

        self.btn_group = QButtonGroup()
        self.btn_group.setExclusive(False)

        self.radio_high = QPushButton(QIcon(get_resource_path("icons/highlighter.svg")), "")
        self.radio_high.setIconSize(QSize(22, 22))
        self.radio_high.setCheckable(True)
        self.radio_high.setChecked(True)
        self.radio_high.setStyleSheet(tool_css)
        self.radio_high.setToolTip("Evidenziatore (E)\nClicca di nuovo oppure premi E per tornare al cursore normale.")

        self.radio_post = QPushButton(QIcon(get_resource_path("icons/sticky_note.svg")), "")
        self.radio_post.setIconSize(QSize(22, 22))
        self.radio_post.setCheckable(True)
        self.radio_post.setStyleSheet(tool_css)
        self.radio_post.setToolTip("Post-it (P)\nTieni premuto Cmd/Ctrl + Click ovunque!")

        self.radio_erase = QPushButton(QIcon(get_resource_path("icons/eraser.svg")), "")
        self.radio_erase.setIconSize(QSize(22, 22))
        self.radio_erase.setCheckable(True)
        self.radio_erase.setStyleSheet(tool_css)
        self.radio_erase.setToolTip("Gomma (Q)")

        self.btn_group.addButton(self.radio_high)
        self.btn_group.addButton(self.radio_post)
        self.btn_group.addButton(self.radio_erase)

        self.btn_group.buttonToggled.connect(self.change_mode)

        self.color_buttons: dict[str, tuple[QPushButton, str]] = {}
        self.current_color = "Giallo"

        self.color_layout = QVBoxLayout()
        self.color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_layout.setSpacing(8)
        self.color_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for name, (hex_code, _) in self.annotation_colors.items():
            self.add_color_button(name, hex_code)
        self.select_color("Giallo")
        palette_widget = QWidget()
        palette_widget.setLayout(self.color_layout)
        palette_widget.setStyleSheet("background: transparent;")
        palette_scroll = QScrollArea()
        palette_scroll.setWidgetResizable(True)
        palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        palette_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        palette_scroll.setWidget(palette_widget)
        self.add_color_btn = QPushButton("+")
        self.add_color_btn.setFixedSize(28, 28)
        self.add_color_btn.setStyleSheet("padding: 0; font-size: 20px;")
        self.add_color_btn.setToolTip("Aggiungi un colore personalizzato")
        self.add_color_btn.clicked.connect(self.choose_custom_color)

        rt_layout.addWidget(self.radio_erase)
        rt_layout.addWidget(self.radio_high)
        rt_layout.addWidget(self.radio_post)
        rt_layout.addWidget(self.add_color_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        rt_layout.addWidget(palette_scroll, 1)

        for key, button in (("E", self.radio_high), ("P", self.radio_post), ("Q", self.radio_erase)):
            QShortcut(QKeySequence(key), self).activated.connect(lambda target=button: self.toggle_tool(target))

    def mode(self) -> str:
        if self.radio_high.isChecked():
            return "highlight"
        if self.radio_post.isChecked():
            return "postit"
        if self.radio_erase.isChecked():
            return "eraser"
        return "pointer"

    def change_mode(self, button: QPushButton, checked: bool) -> None:
        if checked:
            with QSignalBlocker(self.btn_group):
                for other in self.btn_group.buttons():
                    if other is not button:
                        other.setChecked(False)
        self.mode_changed.emit(self.mode())

    def toggle_tool(self, button: QPushButton) -> None:
        if self.is_editing_postit():
            return
        button.setChecked(not button.isChecked())

    def load_custom_colors(self) -> None:
        if not os.path.exists(settings.COLORS_FILE):
            return
        try:
            with open(settings.COLORS_FILE, "r") as f:
                colors = json.load(f)
            if not isinstance(colors, list):
                return
            for value in colors:
                if not isinstance(value, str):
                    continue
                color = QColor(value)
                if color.isValid():
                    hex_code = color.name()
                    if any(existing[0] == hex_code for existing in self.annotation_colors.values()):
                        continue
                    self.annotation_colors[hex_code] = (hex_code, (color.redF(), color.greenF(), color.blueF()))
        except (OSError, ValueError) as error:
            print("Caricamento colori fallito:", error)


    def select_color(self, name: str) -> None:
        self.current_color = name
        for color_name, (button, hex_code) in self.color_buttons.items():
            border = "3px solid #ffffff" if color_name == name else "1px solid #000000"
            text_color = "#ffffff" if QColor(hex_code).lightnessF() < 0.45 else "#111111"
            button.setStyleSheet(f"background-color: {hex_code}; color: {text_color}; border-radius: 12px; border: {border}; padding: 0; font-weight: bold;")


    def add_color_button(self, name: str, hex_code: str) -> None:
        index = len(self.color_buttons)
        key = str((index + 1) % 10) if index < 10 else ""
        button = QPushButton(key)
        button.setFixedSize(24, 24)
        button.setToolTip(f"{name} ({key})" if key else name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, c=name: self.select_color(c))
        self.color_buttons[name] = (button, hex_code)
        self.color_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        if key:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda c=name: self.select_color(c) if not self.is_editing_postit() else None)


    def choose_custom_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.annotation_colors[self.current_color][0]), self,
            "Nuovo colore", QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if not color.isValid():
            return
        hex_code = color.name()
        for name, (existing, _) in self.annotation_colors.items():
            if existing == hex_code:
                self.select_color(name)
                return
        self.annotation_colors[hex_code] = (hex_code, (color.redF(), color.greenF(), color.blueF()))
        self.add_color_button(hex_code, hex_code)
        self.select_color(hex_code)
        try:
            with open(settings.COLORS_FILE + ".tmp", "w") as f:
                json.dump([value[0] for name, value in self.annotation_colors.items() if name not in settings.ANNOTATION_COLORS], f)
            os.replace(settings.COLORS_FILE + ".tmp", settings.COLORS_FILE)
        except OSError as error:
            QMessageBox.warning(self, "Colori personalizzati", f"Non è stato possibile salvare il colore: {error}")
