from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QKeySequence, QTextCharFormat, QTextCursor, QTextDocumentFragment
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem, QMenu


class PostItTextItem(QGraphicsTextItem):
    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paste(self, keep_style: bool = False) -> None:
        clipboard = QApplication.clipboard()
        source = clipboard.mimeData() if clipboard else None
        if source is None or not (source.hasText() or source.hasHtml()):
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if keep_style and source.hasHtml():
            cursor.insertHtml(source.html())
        else:
            text = source.text() if source.hasText() else QTextDocumentFragment.fromHtml(source.html()).toPlainText()
            formatting = QTextCharFormat()
            formatting.setFont(self.font())
            formatting.setForeground(self.defaultTextColor())
            cursor.insertText(text, formatting)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def copy(self) -> None:
        cursor = self.textCursor()
        clipboard = QApplication.clipboard()
        if cursor.hasSelection() and clipboard:
            data = QMimeData()
            data.setText(cursor.selection().toPlainText())
            data.setHtml(cursor.selection().toHtml())
            clipboard.setMimeData(data)

    def delete_selection(self) -> None:
        cursor = self.textCursor()
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    def cut(self) -> None:
        self.copy()
        self.delete_selection()

    def select_all(self) -> None:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)

    def create_context_menu(self) -> QMenu:
        scene = self.scene()
        parent = scene.views()[0] if scene and scene.views() else None
        menu = QMenu(parent)
        document = self.document()
        clipboard = QApplication.clipboard()
        source = clipboard.mimeData() if clipboard else None
        can_paste = source is not None and (source.hasText() or source.hasHtml())
        selected = self.textCursor().hasSelection()

        def add(label: str, callback: Callable[[], None], enabled: bool, key: Any = None) -> None:
            action = menu.addAction(label)
            if action:
                action.triggered.connect(callback)
                action.setEnabled(enabled)
                if key is not None:
                    action.setShortcut(QKeySequence(key))

        if document:
            add("Annulla", document.undo, document.isUndoAvailable(), QKeySequence.StandardKey.Undo)
            add("Ripristina", document.redo, document.isRedoAvailable(), QKeySequence.StandardKey.Redo)
        menu.addSeparator()
        add("Taglia", self.cut, selected, QKeySequence.StandardKey.Cut)
        add("Copia", self.copy, selected, QKeySequence.StandardKey.Copy)
        add("Incolla", self.paste, can_paste, QKeySequence.StandardKey.Paste)
        add("Incolla con lo stesso stile", lambda: self.paste(keep_style=True), can_paste)
        add("Elimina", self.delete_selection, selected)
        menu.addSeparator()
        add("Seleziona tutto", self.select_all, bool(self.toPlainText()), QKeySequence.StandardKey.SelectAll)
        return menu

    def contextMenuEvent(self, event: Any) -> None:
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        menu = self.create_context_menu()
        try:
            menu.exec(event.screenPos())
        finally:
            menu.deleteLater()
        event.accept()
