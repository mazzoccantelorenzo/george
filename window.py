import json
import os
from typing import Any, Optional

from PyQt6.QtCore import QEvent, QSignalBlocker, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QIcon, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget

import settings
from ai_panel import AntigravityPanel
from chat_history import ChatHistory
from pdf_viewer import PDFViewer
from reading_notes import ReadingNotesPanel
from resources import get_resource_path
from theme import DARK_THEME
from tools import ToolPalette
from updater import check_updates
from vault import VaultBrowser


class MainWindow(QMainWindow):
    def __init__(self, root_path: Optional[str] = None, session: Optional[dict[str, Any]] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"George {settings.APP_VERSION}")
        self.resize(1200, 800)
        self.setStyleSheet(DARK_THEME)
        self._postit_keys: set[int] = set()
        self.vault_path = os.path.abspath(root_path) if root_path else None

        self.tools = ToolPalette(lambda: self.viewer.is_editing_postit())
        self.viewer = PDFViewer(self.tools, self)
        self.viewer.previous_page_requested.connect(self.prev_page)
        self.viewer.next_page_requested.connect(self.next_page)
        self.viewer.bookmark_requested.connect(self.toggle_bookmark)
        self.tools.mode_changed.connect(self.change_mode)
        self.viewer.editor.saved.connect(self.save_session)
        self.viewer.editor.changed.connect(self.refresh_reading_notes)
        self.viewer.editor.error.connect(lambda title, message: QMessageBox.warning(self, title, message))

        self.vault_browser = VaultBrowser(root_path)
        self.vault_browser.file_selected.connect(self.open_pdf)
        self.reading_notes = ReadingNotesPanel(lambda: self.viewer.pdf_doc, self.jump_to_note,
            settings.BOOKMARKS_FILE, self.viewer.postit_records)
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setStyleSheet("""
            QTabWidget::pane { background: #252525; border: none; }
            QTabBar::tab { background: #303030; color: #bbbbbb; border: none; padding: 8px 12px; }
            QTabBar::tab:selected { background: #252525; color: #ffffff; }
        """)
        self.sidebar_tabs.addTab(self.vault_browser, "Cartelle")
        self.sidebar_tabs.addTab(self.reading_notes, "Appunti")
        self.reading_notes.bookmarks_changed.connect(self.update_bookmark_icon)
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("Toolbar")
        toolbar_widget.setFixedHeight(40)
        top_layout = QHBoxLayout(toolbar_widget)
        top_layout.setContentsMargins(10, 4, 10, 4)

        btn_save = QPushButton(QIcon(get_resource_path("icons/save.svg")), "")
        btn_save.setIconSize(QSize(16, 16))
        btn_save.clicked.connect(lambda: self.viewer.editor.save_file())
        btn_save.setStyleSheet("background-color: #7a5cfa; border-color: #7a5cfa; color: white;")
        self.undo_button = QPushButton("↶")
        self.undo_button.setToolTip("Annulla ultima modifica (Cmd+Z / Ctrl+Z)")
        self.undo_button.clicked.connect(self.viewer.editor.undo_last_action)

        btn_help = QPushButton(QIcon(get_resource_path("icons/info.svg")), "")
        btn_help.setIconSize(QSize(16, 16))
        btn_help.clicked.connect(self.show_tutorial)
        btn_help.setToolTip("Tutorial & Info")

        self.btn_update = QPushButton(QIcon(get_resource_path("icons/download.svg")), "")
        self.btn_update.setIconSize(QSize(16, 16))
        self.btn_update.clicked.connect(
            lambda: check_updates(self, silent_if_latest=False, on_available=self.mark_update_available)
        )
        self.btn_update.setToolTip("Controlla aggiornamenti di George")

        top_layout.addWidget(btn_save)
        top_layout.addWidget(self.undo_button)
        top_layout.addSpacing(10)
        top_layout.addWidget(btn_help)
        top_layout.addWidget(self.btn_update)
        top_layout.addSpacing(12)
        top_layout.addWidget(QLabel("Pagina"))
        self.page_input = QSpinBox()
        self.page_input.setRange(1, 1)
        self.page_input.setEnabled(False)
        self.page_input.setKeyboardTracking(False)
        self.page_input.setFixedWidth(80)
        self.page_input.setAccessibleName("Pagina del PDF")
        self.page_input.setToolTip("Scrivi il numero della pagina e premi Invio")
        self.page_input.valueChanged.connect(self.go_to_page)
        self.page_count = QLabel("/ —")
        top_layout.addWidget(self.page_input)
        top_layout.addWidget(self.page_count)
        self.viewer.page_changed.connect(self.update_page_counter)
        top_layout.addStretch()
        self.ai_toggle = QPushButton("Antigravity")
        self.ai_toggle.setCheckable(True)
        self.ai_toggle.setChecked(True)
        top_layout.addWidget(self.ai_toggle)

        pdf_and_rt_layout = QHBoxLayout()
        pdf_and_rt_layout.setContentsMargins(0, 0, 0, 0)
        pdf_and_rt_layout.setSpacing(0)
        pdf_and_rt_layout.addWidget(self.viewer)
        pdf_and_rt_layout.addWidget(self.tools)

        pdf_container = QWidget()
        pdf_container.setLayout(pdf_and_rt_layout)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(toolbar_widget)
        right_layout.addWidget(pdf_container)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar_tabs)
        splitter.addWidget(right_widget)
        self.ai_panel = AntigravityPanel(self.ai_context, ChatHistory(settings.CHAT_DIR, self.vault_path))
        splitter.addWidget(self.ai_panel)
        splitter.setSizes([200, 700, 300])
        self.ai_toggle.toggled.connect(self.ai_panel.setVisible)

        self.setCentralWidget(splitter)

        QShortcut(QKeySequence("Right"), self).activated.connect(self.next_page)
        QShortcut(QKeySequence("Left"), self).activated.connect(self.prev_page)
        QShortcut(QKeySequence("A"), self).activated.connect(lambda: self.prev_page() if not self.viewer.is_editing_postit() else None)
        QShortcut(QKeySequence("D"), self).activated.connect(lambda: self.next_page() if not self.viewer.is_editing_postit() else None)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self).activated.connect(self.viewer.editor.undo_last_action)

        # Save è sempre Ctrl+S / Cmd+S per non interferire mai con la scrittura
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.viewer.editor.save_file)

        # Zoom in/out: Cmd++ e Cmd+- (+ e = sono sullo stesso tasto fisico)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.viewer.zoom_by(self.viewer.ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.viewer.zoom_by(self.viewer.ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.viewer.zoom_by(-self.viewer.ZOOM_STEP))

        self.change_mode()
        from PyQt6.QtWidgets import QApplication
        app_inst = QApplication.instance()
        if app_inst: app_inst.installEventFilter(self)

        if session and isinstance(session.get("pdf"), str) and os.path.isfile(session["pdf"]):
            try:
                self.viewer.load_pdf(session["pdf"], int(session.get("page", 0)), float(session.get("zoom", 2.0)))
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                QMessageBox.information(self, "Ultima sessione", f"Non è stato possibile riaprire il PDF: {error}")
        if getattr(settings, "UPDATE_CHECK_ON_STARTUP", False):
            self._update_timer = QTimer(self)
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(
                lambda: check_updates(self, silent_if_latest=True, on_available=self.mark_update_available)
            )
            self._update_timer.start(2500)
        self.save_session()

    def mark_update_available(self, release_info: Any) -> None:
        self.btn_update.setText(f" Aggiorna ({release_info.version})")
        self.btn_update.setStyleSheet(
            "background-color: #16a34a; border-color: #16a34a; color: white; font-weight: bold; padding: 2px 8px;"
        )
        self.btn_update.setToolTip(f"Nuova versione {release_info.version} disponibile! Clicca per aggiornare")

    def ai_context(self) -> tuple[str, str]:
        if not self.viewer.pdf_doc:
            return "", ""
        name = os.path.basename(self.viewer.pdf_doc.name)
        text = self.viewer.selected_text()
        if text:
            return f"Selezione · {name}", text
        page = self.viewer.pdf_doc[self.viewer.current_page_num]
        return f"Pagina {self.viewer.current_page_num + 1} · {name}", page.get_text("text")

    def refresh_reading_notes(self) -> None:
        self.reading_notes.sync_page(self.viewer.current_page_num)
        self.update_bookmark_icon()

    def update_bookmark_icon(self) -> None:
        active = self.reading_notes.is_bookmarked(self.viewer.current_page_num)
        self.viewer.bookmark_button.setChecked(active)
        self.viewer.bookmark_button.setIcon(QIcon(get_resource_path("icons/bookmark-filled.svg" if active else "icons/bookmark.svg")))
        self.viewer.bookmark_button.setToolTip("Rimuovi segnaposto" if active else "Aggiungi segnaposto")
        self.viewer.bookmark_button.setVisible(self.viewer.pdf_doc is not None)

    def toggle_bookmark(self) -> None:
        if not self.viewer.pdf_doc:
            return
        viewport = self.viewer.viewport()
        if viewport is None:
            return
        point = self.viewer.mapToScene(viewport.rect().center())
        try:
            added = self.reading_notes.toggle_bookmark(self.viewer.current_page_num,
                (point.x() / self.viewer.zoom, point.y() / self.viewer.zoom))
            if added:
                self.sidebar_tabs.setCurrentWidget(self.reading_notes)
        except OSError as error:
            self.update_bookmark_icon()
            QMessageBox.warning(self, "Segnaposto", f"Non è stato possibile salvare il segnaposto: {error}")

    def jump_to_note(self, page: int, point: tuple[float, float]) -> None:
        if not self.viewer.pdf_doc:
            return
        self.viewer.editor.save_file()
        self.viewer.current_page_num = page
        self.viewer.render_page()
        self.viewer.centerOn(point[0] * self.viewer.zoom, point[1] * self.viewer.zoom)

    def update_page_counter(self, page: int, total: int) -> None:
        with QSignalBlocker(self.page_input):
            self.page_input.setRange(1, total)
            self.page_input.setValue(page)
        self.page_input.setEnabled(True)
        self.page_count.setText(f"/ {total}")
        self.refresh_reading_notes()
        self.save_session()

    def go_to_page(self, page: int) -> None:
        if not self.viewer.pdf_doc or page == self.viewer.current_page_num + 1:
            return
        self.viewer.editor.save_file()
        self.viewer.current_page_num = page - 1
        self.viewer.render_page()


    def save_session(self) -> None:
        if not self.vault_path:
            return
        session = {"vault": self.vault_path, "pdf": self.viewer.pdf_doc.name if self.viewer.pdf_doc else None,
            "page": self.viewer.current_page_num, "zoom": self.viewer.zoom}
        try:
            with open(settings.SESSION_FILE + ".tmp", "w") as f:
                json.dump(session, f)
            os.replace(settings.SESSION_FILE + ".tmp", settings.SESSION_FILE)
        except OSError as error:
            print("Salvataggio sessione fallito:", error)


    def eventFilter(self, obj: Any, event: Any) -> bool:
        belongs_to_window = obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj))
        if belongs_to_window and event.type() == QEvent.Type.ShortcutOverride and self.viewer.is_editing_postit():
            if event.key() in (Qt.Key.Key_E, Qt.Key.Key_Q, Qt.Key.Key_P, Qt.Key.Key_A, Qt.Key.Key_D) or Qt.Key.Key_0 <= event.key() <= Qt.Key.Key_9:
                event.accept()
                return True
        if belongs_to_window and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
                if not event.isAutoRepeat():
                    if event.type() == QEvent.Type.KeyPress:
                        self._postit_keys.add(event.key())
                    else:
                        self._postit_keys.discard(event.key())
                    self.viewer.postit_modifier = bool(self._postit_keys)
                    self.update_tool_cursor()
        elif event.type() == QEvent.Type.ApplicationDeactivate or (
            event.type() == QEvent.Type.WindowDeactivate
            and (obj is self or obj is self.windowHandle())
        ):
            self._postit_keys.clear()
            self.viewer.postit_modifier = False
            self.update_tool_cursor()
        return super().eventFilter(obj, event)

    def change_mode(self, mode: Optional[str] = None) -> None:
        self.viewer.mode = mode or self.tools.mode()
        self.viewer.clear_text_selection()
        self.update_tool_cursor()

    def update_tool_cursor(self) -> None:
        mode = self.viewer.get_effective_mode()
        icon_name, hotspot = {
            "pointer": ("cursor-pointer", (3, 2)),
            "highlight": ("cursor-highlight", (14, 14)),
            "postit": ("sticky_note", (0, 0)),
            "eraser": ("eraser", (0, 22)),
        }[mode]
        pixmap = QIcon(get_resource_path(f"icons/{icon_name}.svg")).pixmap(QSize(28, 28), 2.0)
        if mode in ("postit", "eraser"):
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor("#ff80bf"))
            painter.end()
        cursor = QCursor(pixmap, *hotspot)
        self.viewer.setCursor(cursor)
        viewport = self.viewer.viewport()
        if viewport:
            viewport.setCursor(cursor)

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "_update_timer"):
            self._update_timer.stop()
        self.ai_panel.shutdown()
        self.vault_browser.shutdown()
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.removeEventFilter(self)
        self._postit_keys.clear()
        self.viewer.postit_modifier = False
        self.viewer.editor.save_file()
        self.save_session()
        self.reading_notes.shutdown()
        super().closeEvent(event)

    def open_pdf(self, path: str) -> None:
        self.viewer.editor.save_file()
        self.viewer.load_pdf(path)

    def show_tutorial(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        msg = f"Benvenuto in George {settings.APP_VERSION}\n\n"
        msg += "📖 STRUMENTI:\n"
        msg += "- Evidenziatore (E): Seleziona il testo per evidenziare; premi di nuovo E per il cursore normale.\n"
        msg += "- Cursore normale: Trascina sul testo del PDF per selezionarlo e copialo con Cmd+C / Ctrl+C.\n"
        msg += "- Post-it (P): Clicca sul PDF per creare un post-it, inizia subito a scrivere.\n"
        msg += "- Dimensioni post-it: Trascina l'angolo in basso a destra. Il testo va a capo e la nota resta abbastanza alta da contenerlo.\n"
        msg += "- Nome post-it: Doppio clic sul nome nell'intestazione per rinominarlo. In Appunti trovi l'elenco dei post-it con nome e pagina.\n"
        msg += "- Gomma (Q): Clicca su un post-it o un highlight per cancellarlo.\n"
        msg += "- Colori: tasti 1–9 e 0, oppure clic sui pallini. Il pulsante + aggiunge un colore personalizzato.\n"
        msg += "- Aggiornamenti (Icona Download): Verifica e scarica automaticamente le nuove versioni di George.\n\n"
        msg += "- Antigravity: Chat laterale sul testo selezionato o sulla pagina corrente. Il pulsante Antigravity mostra o nasconde il pannello; Invio invia la domanda, Shift+Invio va a capo.\n\n"
        msg += "- Chat salvate: La chat si riprende alla riapertura del vault. Il pulsante cronologia riapre le chat precedenti; + ne crea una nuova.\n\n"
        msg += "- File dalla chat: George chiede Consenti/Nega prima delle scritture e dei comandi. Apri i dettagli per leggere l'operazione; il pulsante cartella apre i file creati.\n\n"
        msg += "- Segnaposti: Premi il nastro in alto a destra. In Appunti trovi i segnaposti e le evidenziazioni: un clic ti riporta al punto nel PDF.\n\n"
        msg += "💾 SALVATAGGIO:\n"
        msg += "- Auto-Save: Ogni highlight o modifica viene salvata in tempo reale nel PDF originale.\n"
        msg += "- Ctrl+S / Tasto Floppy: Forza il salvataggio manuale dei post-it attivi.\n\n"
        msg += "⌨️ SHORTCUT:\n"
        msg += "- Cmd+Z / Ctrl+Z: Annulla l'ultima modifica al PDF; nei post-it annulla prima la scrittura.\n"
        msg += "- A / Freccia Sinistra: Pagina precedente. D / Freccia Destra: Pagina successiva.\n"
        msg += "- Pagina: Scrivi il numero nella barra in alto e premi Invio per saltare direttamente.\n"
        msg += "- Canc/Backspace: Elimina il Post-it selezionato (cliccando sul bordo esterno)."
        QMessageBox.information(self, "Tutorial di George", msg)

    def prev_page(self) -> None:
        if self.viewer.pdf_doc and self.viewer.current_page_num > 0:
            self.viewer.editor.save_file()
            self.viewer.current_page_num -= 1
            self.viewer.render_page()

    def next_page(self) -> None:
        if self.viewer.pdf_doc and self.viewer.current_page_num < len(self.viewer.pdf_doc) - 1:
            self.viewer.editor.save_file()
            self.viewer.current_page_num += 1
            self.viewer.render_page()
