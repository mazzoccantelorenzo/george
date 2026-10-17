import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFileSystemModel, QPixmap
from PyQt6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QTreeView, QVBoxLayout, QWidget, QMessageBox

import settings
from resources import get_resource_path


def find_vault_paths(root: str, query: str, cancelled: Event) -> list[str]:
    matches: list[str] = []
    for folder, dirs, files in os.walk(root):
        if cancelled.is_set():
            break
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for name in dirs + sorted(name for name in files if name.lower().endswith(".pdf")):
            if cancelled.is_set():
                return matches
            path = os.path.join(folder, name)
            if query.casefold() in os.path.relpath(path, root).casefold():
                matches.append(path)
                if len(matches) == 200:
                    return matches
    return matches


class VaultItemWidget(QWidget):
    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)

        name_label = QLabel(os.path.basename(path) or path)
        name_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #e0e0e0; background: transparent;")

        path_label = QLabel(path)
        path_label.setStyleSheet("font-size: 12px; color: #888888; background: transparent;")

        layout.addWidget(name_label)
        layout.addWidget(path_label)
        self.setLayout(layout)


class VaultSelector(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"George {settings.APP_VERSION} - Vaults")
        self.setFixedSize(700, 480)
        self.setStyleSheet("background-color: #1e1e1e; color: #e0e0e0;")

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)

        left_panel = QVBoxLayout()
        header = QLabel(f"George {settings.APP_VERSION}")
        header.setStyleSheet("font-size: 20px; font-weight: 600; color: #ffffff;")

        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("""
            QListWidget {
                background-color: #252525;
                border: 1px solid #333333;
                border-radius: 8px;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #333333;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #363636;
            }
        """)
        self.recent_list.itemDoubleClicked.connect(self.on_item_double_click)
        self.load_recent_vaults()

        self.vault_search = QLineEdit()
        self.vault_search.setPlaceholderText("Cerca nei vault recenti…")
        self.vault_search.setClearButtonEnabled(True)
        self.vault_search.textChanged.connect(self.filter_recent_vaults)

        left_panel.addWidget(header)
        left_panel.addSpacing(15)
        left_panel.addWidget(self.vault_search)
        left_panel.addWidget(self.recent_list)

        right_panel = QVBoxLayout()
        right_panel.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_path = get_resource_path("icon_fixed.png")
        icon_pixmap = QPixmap(icon_path).scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_open = QPushButton("Open folder as vault")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: #7a5cfa;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #8c73ff;
            }
        """)
        btn_open.clicked.connect(self.select_folder)

        self.last_session = settings.load_last_session()
        if not self.last_session and self.recent_list.count():
            recent_item = self.recent_list.item(0)
            if recent_item:
                self.last_session = {"vault": recent_item.data(Qt.ItemDataRole.UserRole)}
        self.resume_session: Optional[dict[str, Any]] = None
        vault = self.last_session.get("vault")
        self.resume_button = QPushButton("Riprendi ultima sessione")
        self.resume_button.setEnabled(isinstance(vault, str) and os.path.isdir(vault))
        self.resume_button.setToolTip("Riapre l'ultimo vault e, se salvati, il PDF e la pagina dove eri rimasto.")
        self.resume_button.clicked.connect(self.resume_last_session)

        right_panel.addSpacing(40)
        right_panel.addWidget(self.resume_button)
        right_panel.addWidget(icon_label)
        right_panel.addSpacing(40)
        right_panel.addWidget(btn_open)

        main_layout.addLayout(left_panel, 60)
        main_layout.addSpacing(25)
        main_layout.addLayout(right_panel, 40)

        self.setLayout(main_layout)
        self.selected_path: Optional[str] = None

    def filter_recent_vaults(self, query: str) -> None:
        for i in range(self.recent_list.count()):
            item = self.recent_list.item(i)
            if item:
                item.setHidden(query.casefold() not in item.data(Qt.ItemDataRole.UserRole).casefold())

    def resume_last_session(self) -> None:
        vault = self.last_session.get("vault")
        if not isinstance(vault, str) or not os.path.isdir(vault):
            QMessageBox.information(self, "Ultima sessione", "La cartella dell'ultima sessione non è più disponibile.")
            return
        self.selected_path = vault
        self.resume_session = self.last_session
        self.save_recent_vault(vault)
        self.accept()

    def load_recent_vaults(self) -> None:
        try:
            with open(settings.HISTORY_FILE, "r") as f:
                recent = json.load(f)
                for path in recent:
                    if os.path.exists(path):
                        item = QListWidgetItem(self.recent_list)
                        widget = VaultItemWidget(path)
                        item.setSizeHint(widget.sizeHint())
                        item.setData(Qt.ItemDataRole.UserRole, path)
                        self.recent_list.setItemWidget(item, widget)
        except Exception:
            pass

    def save_recent_vault(self, path: str) -> None:
        try:
            with open(settings.HISTORY_FILE, "r") as f:
                recent = json.load(f)
        except Exception:
            recent = []

        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]

        with open(settings.HISTORY_FILE, "w") as f:
            json.dump(recent, f)

    def on_item_double_click(self, item: QListWidgetItem) -> None:
        self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.save_recent_vault(self.selected_path)
        self.accept()

    def select_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder as vault")
        if path:
            self.selected_path = path
            self.save_recent_vault(path)
            self.accept()


class VaultBrowser(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, root_path: Optional[str] = None) -> None:
        super().__init__()
        self.vault_path = os.path.abspath(root_path) if root_path else None
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(root_path or "")
        self.sidebar = QTreeView()
        self.sidebar.setModel(self.file_model)
        self.sidebar.setRootIndex(self.file_model.index(root_path or ""))
        self.sidebar.setColumnWidth(0, 200)
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAlternatingRowColors(False)
        for column in range(1, 4):
            self.sidebar.hideColumn(column)
        self.sidebar.doubleClicked.connect(self.open_file)
        self.folder_search = QLineEdit()
        self.folder_search.setPlaceholderText("Cerca cartelle e PDF…")
        self.folder_search.setClearButtonEnabled(True)
        self.folder_search.setStyleSheet("background: #252525; color: #dddddd; padding: 8px; border: 1px solid #444444;")
        self.search_results = QListWidget()
        self.search_results.setStyleSheet("background: #252525; color: #dddddd; border: none;")
        self.search_results.itemDoubleClicked.connect(self.open_search_result)
        self.sidebar_views = QStackedWidget()
        self.sidebar_views.addWidget(self.sidebar)
        self.sidebar_views.addWidget(self.search_results)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.folder_search)
        layout.addWidget(self.sidebar_views)
        self.search_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="george-search")
        self.search_future: Optional[Any] = None
        self.search_cancelled = Event()
        self.search_debounce = QTimer(self)
        self.search_debounce.setSingleShot(True)
        self.search_debounce.setInterval(250)
        self.search_debounce.timeout.connect(self.start_folder_search)
        self.search_poll = QTimer(self)
        self.search_poll.setInterval(50)
        self.search_poll.timeout.connect(self.poll_folder_search)
        self.folder_search.textChanged.connect(self.queue_folder_search)


    def queue_folder_search(self, query: str) -> None:
        if query.strip():
            self.search_debounce.start()
        else:
            self.search_debounce.stop()
            self.start_folder_search()


    def start_folder_search(self) -> None:
        self.search_cancelled.set()
        if self.search_future:
            self.search_future.cancel()
        self.search_future = None
        self.search_poll.stop()
        query = self.folder_search.text().strip()
        self.search_results.clear()
        if not query or not self.vault_path:
            self.sidebar_views.setCurrentWidget(self.sidebar)
            return
        self.sidebar_views.setCurrentWidget(self.search_results)
        pending = QListWidgetItem("Ricerca…", self.search_results)
        pending.setFlags(Qt.ItemFlag.NoItemFlags)
        self.search_cancelled = Event()
        self.search_future = self.search_executor.submit(find_vault_paths, self.vault_path, query, self.search_cancelled)
        self.search_poll.start()


    def poll_folder_search(self) -> None:
        if self.search_future is None or not self.search_future.done():
            return
        self.search_poll.stop()
        paths = self.search_future.result()
        self.search_future = None
        self.search_results.clear()
        for path in paths:
            name = os.path.relpath(path, self.vault_path or "")
            item = QListWidgetItem(("📁 " if os.path.isdir(path) else "📄 ") + name, self.search_results)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
        if not paths:
            empty = QListWidgetItem("Nessuna cartella o PDF trovato", self.search_results)
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
        elif len(paths) == 200:
            limit = QListWidgetItem("Primi 200 risultati: specifica meglio la ricerca", self.search_results)
            limit.setFlags(Qt.ItemFlag.NoItemFlags)


    def open_search_result(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(path, str):
            return
        if os.path.isdir(path):
            self.folder_search.clear()
            index = self.file_model.index(path)
            parent = index.parent()
            while parent.isValid() and parent != self.sidebar.rootIndex():
                self.sidebar.expand(parent)
                parent = parent.parent()
            self.sidebar.setCurrentIndex(index)
            self.sidebar.expand(index)
            self.sidebar.scrollTo(index)
        elif os.path.isfile(path):
            self.file_selected.emit(path)


    def open_file(self, index: Any) -> None:
        path = self.file_model.filePath(index)
        if path.lower().endswith(".pdf"):
            self.file_selected.emit(path)

    def shutdown(self) -> None:
        self.search_debounce.stop()
        self.search_poll.stop()
        self.search_cancelled.set()
        if self.search_future:
            self.search_future.cancel()
        self.search_executor.shutdown(wait=False, cancel_futures=True)
