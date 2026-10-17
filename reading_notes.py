import json
import os
from collections.abc import Callable
from typing import Any, Optional

import fitz
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


def extract_highlight(page: Any, annotation: Any) -> tuple[str, tuple[float, float]]:
    vertices = annotation.vertices or []
    areas = [fitz.Quad(vertices[i:i + 4]).rect for i in range(0, len(vertices), 4)]
    if not areas:
        areas = [annotation.rect]
    words = [word for word in page.get_text("words", sort=True)
        if any(fitz.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2) in area for area in areas)]
    text = ""
    previous = None
    for word in words:
        if previous:
            text += " " if previous[5:7] == word[5:7] else "\n"
        text += word[4]
        previous = word
    target = areas[0]
    point = fitz.Point((target.x0 + target.x1) / 2, (target.y0 + target.y1) / 2) * page.rotation_matrix
    return text or "Testo evidenziato", (point.x, point.y)


class HighlightCard(QWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()
        else:
            super().mouseReleaseEvent(event)


class ReadingNotesPanel(QWidget):
    bookmarks_changed = pyqtSignal()

    def __init__(self, document: Callable[[], Any], jump: Callable[[int, tuple[float, float]], None], bookmarks_file: str, live_postits: Optional[Callable[[], list[dict[str, Any]]]] = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.document = document
        self.jump = jump
        self.live_postits = live_postits
        self.bookmarks_file = bookmarks_file
        self.bookmarks: dict[str, list[dict[str, Any]]] = {}
        try:
            with open(bookmarks_file) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.bookmarks = saved
        except (OSError, ValueError):
            pass
        self.scanned_document: Optional[Any] = None
        self.highlights: dict[int, list[dict[str, Any]]] = {}
        self.postits: dict[int, list[dict[str, Any]]] = {}
        self.postit_items: dict[tuple[int, int], QListWidgetItem] = {}
        self.cards: dict[tuple[int, int], tuple[QListWidgetItem, HighlightCard]] = {}
        self.scan_page = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scan_batch)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.addWidget(QLabel("Segnaposti"))
        self.bookmark_list = QListWidget()
        self.bookmark_list.setMaximumHeight(150)
        self.bookmark_list.itemClicked.connect(self.open_item)
        layout.addWidget(self.bookmark_list)
        self.postit_label = QLabel("Post-it")
        layout.addWidget(self.postit_label)
        self.postit_list = QListWidget()
        self.postit_list.setMaximumHeight(220)
        self.postit_list.itemClicked.connect(self.open_item)
        layout.addWidget(self.postit_list)
        self.highlight_label = QLabel("Evidenziazioni")
        layout.addWidget(self.highlight_label)
        self.highlight_list = QListWidget()
        self.highlight_list.setSpacing(5)
        self.highlight_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.highlight_list.itemClicked.connect(self.open_item)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.layout_cards)
        viewport = self.highlight_list.viewport()
        if viewport:
            viewport.installEventFilter(self)
        layout.addWidget(self.highlight_list, 1)
        self.setStyleSheet("""
            ReadingNotesPanel { background: #252525; }
            QLabel { color: #dddddd; background: transparent; }
            QListWidget { background: #252525; color: #dddddd; border: none; }
            QListWidget::item:selected { background: #444444; }
        """)

    def current_bookmarks(self) -> list[dict[str, Any]]:
        document = self.document()
        if document is None or document.is_closed:
            return []
        records = self.bookmarks.get(os.path.abspath(document.name), [])
        if not isinstance(records, list):
            return []
        return [record for record in records if isinstance(record, dict)
            and isinstance(record.get("page"), int) and 0 <= record["page"] < len(document)
            and isinstance(record.get("point"), list) and len(record["point"]) == 2
            and all(isinstance(value, (int, float)) for value in record["point"])]

    def is_bookmarked(self, page: int) -> bool:
        return any(record["page"] == page for record in self.current_bookmarks())

    def toggle_bookmark(self, page: int, point: tuple[float, float]) -> bool:
        document = self.document()
        if document is None or document.is_closed:
            return False
        records = self.current_bookmarks()
        added = not self.is_bookmarked(page)
        records = [record for record in records if record["page"] != page]
        if added:
            records.append({"page": page, "point": list(point)})
        updated = dict(self.bookmarks)
        updated[os.path.abspath(document.name)] = records
        with open(self.bookmarks_file + ".tmp", "w") as f:
            json.dump(updated, f)
        os.replace(self.bookmarks_file + ".tmp", self.bookmarks_file)
        self.bookmarks = updated
        self.refresh_bookmarks()
        self.bookmarks_changed.emit()
        return added

    def refresh_bookmarks(self) -> None:
        self.bookmark_list.clear()
        for record in sorted(self.current_bookmarks(), key=lambda value: value["page"]):
            item = QListWidgetItem(f"🔖 Pagina {record['page'] + 1}", self.bookmark_list)
            item.setData(Qt.ItemDataRole.UserRole, record)
        if not self.bookmark_list.count():
            item = QListWidgetItem("Nessun segnaposto", self.bookmark_list)
            item.setFlags(Qt.ItemFlag.NoItemFlags)

    def sync_page(self, page: int) -> None:
        document = self.document()
        if document is None or document.is_closed:
            return
        if document is not self.scanned_document:
            self.scanned_document = document
            self.highlights.clear()
            self.highlight_list.clear()
            self.cards.clear()
            self.postits.clear()
            self.postit_items.clear()
            self.postit_list.clear()
            self.scan_page = 0
            self.timer.start(0)
        self.highlights[page] = self.read_page(document, page)
        if self.live_postits:
            self.postits[page] = self.live_postits()
        self.refresh_bookmarks()
        self.refresh_highlights()
        self.refresh_postits()

    def read_page(self, document: Any, index: int) -> list[dict[str, Any]]:
        page = document[index]
        records = []
        postits = []
        for annotation in page.annots():
            if annotation.type[0] == fitz.PDF_ANNOT_HIGHLIGHT:
                text, point = extract_highlight(page, annotation)
                color = annotation.colors.get("stroke") or (0.98, 0.93, 0.65)
                records.append({"id": annotation.xref, "page": index, "point": point, "text": text, "color": color})
            elif annotation.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                point = (annotation.rect.tl + (annotation.rect.br - annotation.rect.tl) / 2) * page.rotation_matrix
                postits.append({"id": annotation.xref, "page": index, "point": (point.x, point.y),
                    "title": annotation.info.get("subject") or "Post-it",
                    "text": annotation.info.get("content", ""),
                    "color": annotation.colors.get("fill") or annotation.colors.get("stroke") or (0.98, 0.93, 0.65)})
        self.postits[index] = postits
        return records

    def scan_batch(self) -> None:
        document = self.document()
        if document is None or document.is_closed or document is not self.scanned_document:
            self.timer.stop()
            return
        updated = False
        for _ in range(12):
            if self.scan_page >= len(document):
                self.timer.stop()
                break
            index = self.scan_page
            self.scan_page += 1
            if index not in self.highlights:
                self.highlights[index] = self.read_page(document, index)
                updated = updated or bool(self.highlights[index]) or bool(self.postits[index])
        if updated:
            self.refresh_highlights()
            self.refresh_postits()

    def refresh_postits(self) -> None:
        records = [record for page in sorted(self.postits) for record in self.postits[page]]
        keys = {(record["page"], record["id"]) for record in records}
        for key in list(self.postit_items):
            if key not in keys:
                removed_item = self.postit_items.pop(key)
                self.postit_list.takeItem(self.postit_list.row(removed_item))
        for row in range(self.postit_list.count() - 1, -1, -1):
            placeholder = self.postit_list.item(row)
            if placeholder and placeholder.data(Qt.ItemDataRole.UserRole) is None:
                self.postit_list.takeItem(row)
        for row, record in enumerate(records):
            key = (record["page"], record["id"])
            item = self.postit_items.get(key)
            if item is None:
                item = QListWidgetItem()
                self.postit_list.insertItem(row, item)
                self.postit_items[key] = item
            preview = " ".join(record["text"].split())
            item.setText(f"{record['title']} · Pagina {record['page'] + 1}\n{preview[:80]}")
            item.setToolTip(record["text"])
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setForeground(QColor("#eeeeee"))
            color = QColor.fromRgbF(*record["color"][:3])
            color.setAlpha(35)
            item.setBackground(color)
        self.postit_label.setText(f"Post-it ({len(records)})")
        if not records:
            placeholder = QListWidgetItem("Nessun post-it", self.postit_list)
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.layout_timer.start(0)
        return super().eventFilter(obj, event)

    def refresh_highlights(self) -> None:
        scrollbar = self.highlight_list.verticalScrollBar()
        position = scrollbar.value() if scrollbar else 0
        records = [record for index in sorted(self.highlights) for record in self.highlights[index]]
        indexed = {(record["page"], record["id"]): record for record in records}
        for key in list(self.cards):
            item, card = self.cards[key]
            record = indexed.get(key)
            if record is None or item.data(Qt.ItemDataRole.UserRole) != record:
                self.cards.pop(key)
                self.highlight_list.removeItemWidget(item)
                self.highlight_list.takeItem(self.highlight_list.row(item))
                card.deleteLater()
        for row in range(self.highlight_list.count() - 1, -1, -1):
            placeholder_item = self.highlight_list.item(row)
            if placeholder_item and placeholder_item.data(Qt.ItemDataRole.UserRole) is None:
                self.highlight_list.takeItem(row)
        row = 0
        for index in sorted(self.highlights):
            for record in self.highlights[index]:
                key = (index, record["id"])
                if key in self.cards:
                    row += 1
                    continue
                item = QListWidgetItem()
                self.highlight_list.insertItem(row, item)
                row += 1
                item.setData(Qt.ItemDataRole.UserRole, record)
                item.setToolTip(record["text"])
                card = HighlightCard()
                card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.setToolTip(record["text"])
                card.clicked.connect(lambda data=record: self.jump(data["page"], tuple(data["point"])))
                color = QColor.fromRgbF(*record["color"][:3])
                red, green, blue, _ = color.getRgb()
                card.setStyleSheet(f"background: rgba({red}, {green}, {blue}, 35); border-left: 3px solid {color.name()}; border-radius: 5px;")
                layout = QVBoxLayout(card)
                layout.setContentsMargins(9, 8, 9, 8)
                page_label = QLabel(f"Pagina {index + 1}")
                page_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                page_label.setStyleSheet("font-size: 11px; color: #aaaaaa; background: transparent; border: none;")
                layout.addWidget(page_label)
                text = record["text"]
                label = QLabel(text[:180] + ("…" if len(text) > 180 else ""))
                label.setObjectName("highlightText")
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                viewport = self.highlight_list.viewport()
                label.setFixedWidth(max(80, viewport.width() - 32) if viewport else 160)
                label.setStyleSheet("color: #eeeeee; background: transparent; border: none;")
                layout.addWidget(label)
                item.setSizeHint(card.sizeHint())
                self.highlight_list.setItemWidget(item, card)
                self.cards[key] = (item, card)
        self.layout_cards()
        count = len(records)
        self.highlight_label.setText(f"Evidenziazioni ({count})")
        if not count:
            item = QListWidgetItem("Nessuna evidenziazione", self.highlight_list)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
        if scrollbar:
            scrollbar.setValue(position)

    def layout_cards(self) -> None:
        viewport = self.highlight_list.viewport()
        width = max(80, viewport.width() - 32) if viewport else 160
        for item, card in self.cards.values():
            label = card.findChild(QLabel, "highlightText")
            if label:
                label.setFixedWidth(width)
                item.setSizeHint(card.sizeHint())

    def open_item(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self.jump(record["page"], tuple(record["point"]))

    def shutdown(self) -> None:
        self.timer.stop()
        self.layout_timer.stop()
