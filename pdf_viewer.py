from typing import Any, Optional, TYPE_CHECKING, cast

import fitz
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QImage, QKeySequence, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QPushButton, QWidget

import settings
from document_editor import DocumentEditor
from postits import PostItItem

if TYPE_CHECKING:
    from tools import ToolPalette


class FloatingButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 60);
                color: rgba(255, 255, 255, 180);
                font-size: 30px;
                font-weight: bold;
                border: none;
                border-radius: 20px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 200);
                color: white;
            }
        """)
        self.setFixedSize(50, 80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class PDFViewer(QGraphicsView):
    page_changed = pyqtSignal(int, int)
    previous_page_requested = pyqtSignal()
    next_page_requested = pyqtSignal()
    bookmark_requested = pyqtSignal()

    def __init__(self, tools: "ToolPalette", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tools = tools
        self.postit_modifier = False
        self.editor = DocumentEditor(self)
        self.scene_obj = QGraphicsScene(self)
        self.scene_obj.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.pdf_doc = None
        self.current_page_num = 0
        self.zoom = 2.0
        self.mode = "highlight"


        self.start_pos = None
        self.current_rect_item = None

        self.words: list[Any] = []
        self.start_word_idx = -1
        self.highlight_items: list[QGraphicsRectItem] = []
        self.text_selection: Optional[tuple[int, int]] = None
        self.selection_anchor = -1

        self.btn_prev = FloatingButton("‹", self)
        self.btn_next = FloatingButton("›", self)
        self.btn_prev.clicked.connect(lambda: self.previous_page_requested.emit())
        self.btn_next.clicked.connect(lambda: self.next_page_requested.emit())
        self.btn_prev.hide()
        self.btn_next.hide()
        self.bookmark_button = QPushButton(self)
        self.bookmark_button.setCheckable(True)
        self.bookmark_button.setFixedSize(36, 42)
        self.bookmark_button.setIconSize(QSize(24, 28))
        self.bookmark_button.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.bookmark_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bookmark_button.clicked.connect(lambda: self.bookmark_requested.emit())
        self.bookmark_button.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_prev.move(10, (self.height() - self.btn_prev.height()) // 2)
        self.btn_next.move(self.width() - self.btn_next.width() - 30, (self.height() - self.btn_next.height()) // 2)
        self.bookmark_button.move(self.width() - 56, 8)

    ZOOM_MIN: float = 0.5
    ZOOM_MAX: float = 5.0
    ZOOM_STEP: float = 0.1

    def zoom_by(self, delta: float) -> None:
        """Change zoom by delta (e.g. +0.1 or -0.1), clamp, re-render."""
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom + delta))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        self.editor.save_file()
        self.zoom = new_zoom
        self.render_page()

    def wheelEvent(self, event: Any) -> None:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        modifiers = QApplication.keyboardModifiers()
        is_cmd = bool(
            (modifiers & Qt.KeyboardModifier.ControlModifier)
            or (modifiers & Qt.KeyboardModifier.MetaModifier)
        )
        if is_cmd and self.pdf_doc:
            # One notch up = +10 %, down = -10 %
            delta = self.ZOOM_STEP if event.angleDelta().y() > 0 else -self.ZOOM_STEP
            self.zoom_by(delta)
            event.accept()
        else:
            super().wheelEvent(event)

    def load_pdf(self, path: str, page: int = 0, zoom: float = 2.0) -> None:
        document = fitz.open(path)
        if self.pdf_doc is not None and not self.pdf_doc.is_closed:
            self.pdf_doc.close()
        self.pdf_doc = document
        self.current_page_num = max(0, min(page, len(document) - 1))
        self.zoom = max(self.ZOOM_MIN, min(zoom, self.ZOOM_MAX))
        self.editor.undo_stack.clear()
        self.editor.page_states.clear()
        with open(path, "rb") as f:
            self.editor.last_saved_pdf = f.read()
        self.btn_prev.show()
        self.btn_next.show()
        self.render_page()
        self.editor.page_states[self.current_page_num] = self.editor.annotation_state()

    def render_page(self) -> None:
        if not self.pdf_doc: return
        previous_scene = self.scene_obj
        self.start_pos = None
        self.start_word_idx = -1
        self.current_rect_item = None
        self.highlight_items.clear()
        self.clear_text_selection()
        # Keep native items alive until the current Qt input/paint event finishes.
        for item in previous_scene.items():
            if isinstance(item, PostItItem):
                doc = item.text_item.document()
                if doc:
                    doc.contentsChanged.disconnect(item.update_rect)
        self.scene_obj = QGraphicsScene(self)
        # Qt's BSP index can retain deleted post-it children after a close/undo.
        # Pages have few live items; a linear index suits these changing objects.
        self.scene_obj.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self.scene_obj)
        previous_scene.deleteLater()
        page = cast(Any, self.pdf_doc)[self.current_page_num]

        self.words = page.get_text("words")

        postits_to_create = []
        if page.first_annot:
            annot = page.first_annot
            while annot:
                next_annot = annot.next
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    rect = annot.rect
                    text = annot.info.get("content", "")
                    color_vals = annot.colors.get("fill")
                    if not color_vals: color_vals = annot.colors.get("stroke")
                    if not color_vals: color_vals = [0.98, 0.93, 0.65]

                    postits_to_create.append({
                        "text": text,
                        "title": annot.info.get("subject") or "Post-it",
                        "rect": rect,
                        "pdf_color": tuple(color_vals)
                    })
                    page.delete_annot(annot)
                annot = next_annot

        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)
        samples = pix.samples
        img = QImage(samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        self.scene_obj.addPixmap(pixmap)
        self.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        for p in postits_to_create:
            pdf_c = p["pdf_color"]
            hex_color = next((color[0] for color in self.tools.annotation_colors.values()
                if all(abs(actual - expected) < 0.00001 for actual, expected in zip(pdf_c, color[1]))),
                f"#{round(pdf_c[0]*255):02x}{round(pdf_c[1]*255):02x}{round(pdf_c[2]*255):02x}")
            x = p["rect"].x0 * self.zoom
            scale = self.zoom / 2
            y = (p["rect"].y0 * self.zoom) - 24 * scale
            postit = PostItItem(p["text"], x, y, bg_color=hex_color, pdf_color=pdf_c,
                width=p["rect"].width * 2, height=p["rect"].height * 2 + 24, title=p["title"])
            postit.setScale(scale)
            self.scene_obj.addItem(postit)
        self.editor.page_states.setdefault(self.current_page_num, self.editor.annotation_state())
        self.page_changed.emit(self.current_page_num + 1, len(self.pdf_doc))

    def save_pdf(self, path):
        if self.pdf_doc:
            self.pdf_doc.save(path)

    def get_word_index_at(self, pos: QPointF) -> int:
        if not self.words: return -1
        x, y = pos.x() / self.zoom, pos.y() / self.zoom

        best_idx = -1
        min_dist = float('inf')

        for i, w in enumerate(self.words):
            wx0, wy0, wx1, wy1 = w[:4]
            if wx0 <= x <= wx1 and wy0 <= y <= wy1:
                return i
            cx, cy = (wx0+wx1)/2, (wy0+wy1)/2
            dist = (cx-x)**2 + (cy-y)**2
            if dist < min_dist:
                min_dist = dist
                best_idx = i

        if min_dist < 2000:
            return best_idx
        return -1


    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Undo):
            self.editor.undo_last_action()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy) and not self.is_editing_postit():
            if self.text_selection is not None:
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(self.selected_text())
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            focus_item = self.scene_obj.focusItem()
            if focus_item and hasattr(focus_item, "textInteractionFlags"):
                super().keyPressEvent(event)
                return

            # Altrimenti cancella i post-it selezionati (bordo esterno cliccato)
            if self.scene_obj.selectedItems():
                self.editor.save_file()
            deleted = False
            for item in self.scene_obj.selectedItems():
                if item.data(100) == "postit":
                    cast(PostItItem, item).remove_from_scene()
                    deleted = True
            if deleted:
                self.editor.save_file()

        super().keyPressEvent(event)

    def get_effective_mode(self) -> str:
        return "postit" if self.postit_modifier else self.mode

    def clear_text_selection(self) -> None:
        self.text_selection = None
        self.selection_anchor = -1
        viewport = self.viewport()
        if viewport:
            viewport.update()

    def select_text_to(self, end: int) -> None:
        if self.selection_anchor == -1 or end == -1:
            return
        self.text_selection = (min(self.selection_anchor, end), max(self.selection_anchor, end))
        viewport = self.viewport()
        if viewport:
            viewport.update()

    def selected_text(self) -> str:
        if self.text_selection is None:
            return ""
        start, end = self.text_selection
        words = self.words[start:end + 1]
        text = words[0][4]
        previous = words[0]
        for word in words[1:]:
            text += (" " if previous[5:7] == word[5:7] else "\n") + word[4]
            previous = word
        return text

    def drawForeground(self, painter: Any, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self.text_selection is None:
            return
        start, end = self.text_selection
        # This overlay is temporary and never becomes a PDF annotation or scene item.
        for word in self.words[start:end + 1]:
            selection_rect = QRectF(word[0] * self.zoom, word[1] * self.zoom,
                (word[2] - word[0]) * self.zoom, (word[3] - word[1]) * self.zoom)
            painter.fillRect(selection_rect, QColor(60, 140, 255, 90))

    def mousePressEvent(self, event: Any) -> None:
        if not self.pdf_doc: return
        pos = self.mapToScene(event.pos())
        self.clear_text_selection()
        item = self.scene_obj.itemAt(pos, self.transform())

        if self.mode == "eraser":
            self.editor.save_file()
            items_at_pos = self.scene_obj.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, self.transform())
            deleted = False
            for it in items_at_pos:
                if it.data(100) == "postit":
                    cast(PostItItem, it).remove_from_scene()
                    deleted = True
                    break
                elif it.data(100) == "postit_text":
                    cast(PostItItem, it.parentItem()).remove_from_scene()
                    deleted = True
                    break

            if deleted:
                self.editor.save_file()
                return

            p = fitz.Point(pos.x() / self.zoom, pos.y() / self.zoom)
            page = cast(Any, self.pdf_doc)[self.current_page_num]
            if page.first_annot:
                for annot in page.annots():
                    if annot.rect.contains(p):
                        page.delete_annot(annot)
                        self.editor.save_file()
                        self.render_page()
                        return
            return

        # itemAt() returns the topmost Z-order item (even with NoButton children).
        # QGraphicsSceneMouseEvent cannot be instantiated from Python, so we cannot call
        # PostItItem.mousePressEvent directly with the right type.
        # Instead: find the PostItItem ancestor and call its action logic directly.
        def find_postit_ancestor(it: Any) -> Any:
            while it is not None:
                if isinstance(it, PostItItem):
                    return it
                it = it.parentItem()
            return None

        postit_ancestor = find_postit_ancestor(item)
        if postit_ancestor is not None:
            consumed = postit_ancestor.handle_click(pos)
            if consumed:
                return
            # Not consumed (plain header/body click) → let Qt handle drag via ItemIsMovable
            super().mousePressEvent(event)
            return

        if item and item.data(100) == "postit_text":
            super().mousePressEvent(event)
            return

        if self.get_effective_mode() == "pointer":
            super().mousePressEvent(event)
            if event.button() == Qt.MouseButton.LeftButton:
                self.scene_obj.clearFocus()
                x, y = pos.x() / self.zoom, pos.y() / self.zoom
                self.selection_anchor = next((i for i, word in enumerate(self.words)
                    if word[0] <= x <= word[2] and word[1] <= y <= word[3]), -1)
                self.select_text_to(self.selection_anchor)
            return

        self.start_pos = pos
        self.editor.save_file()
        if self.get_effective_mode() == "highlight":
            self.start_word_idx = self.get_word_index_at(pos)
        else:
            self.start_word_idx = -1

    def mouseMoveEvent(self, event: Any) -> None:
        super().mouseMoveEvent(event)
        if self.get_effective_mode() == "pointer" and event.buttons() & Qt.MouseButton.LeftButton:
            self.select_text_to(self.get_word_index_at(self.mapToScene(event.pos())))
            return
        if not self.start_pos: return
        pos = self.mapToScene(event.pos())

        if self.get_effective_mode() == "highlight" and self.start_word_idx != -1:
            end_word_idx = self.get_word_index_at(pos)
            if end_word_idx != -1:
                for it in self.highlight_items:
                    self.scene_obj.removeItem(it)
                self.highlight_items.clear()

                start_i = min(self.start_word_idx, end_word_idx)
                end_i = max(self.start_word_idx, end_word_idx)

                for i in range(start_i, end_i + 1):
                    w = self.words[i]
                    rect = QRectF(w[0]*self.zoom, w[1]*self.zoom, (w[2]-w[0])*self.zoom, (w[3]-w[1])*self.zoom)
                    r_item = QGraphicsRectItem(rect)
                    color = QColor(self.tools.annotation_colors[self.tools.current_color][0])
                    color.setAlpha(100)
                    r_item.setBrush(QBrush(color))
                    r_item.setPen(QPen(Qt.PenStyle.NoPen))
                    self.scene_obj.addItem(r_item)
                    self.highlight_items.append(r_item)


    def mouseReleaseEvent(self, event: Any) -> None:
        super().mouseReleaseEvent(event)
        if self.selection_anchor != -1 and event.button() == Qt.MouseButton.LeftButton:
            self.select_text_to(self.get_word_index_at(self.mapToScene(event.pos())))
            self.selection_anchor = -1
            return
        if not self.start_pos: return
        pos = self.mapToScene(event.pos())

        effective_mode = self.get_effective_mode()

        if effective_mode == "highlight" and self.start_word_idx != -1:
            end_word_idx = self.get_word_index_at(pos)
            if end_word_idx != -1:
                start_i = min(self.start_word_idx, end_word_idx)
                end_i = max(self.start_word_idx, end_word_idx)

                quads = []
                for i in range(start_i, end_i + 1):
                    w = self.words[i]
                    quads.append(fitz.Rect(w[:4]).quad)


                page = cast(Any, self.pdf_doc)[self.current_page_num]
                annot = page.add_highlight_annot(quads)
                annot.set_colors(stroke=self.tools.annotation_colors[self.tools.current_color][1])
                annot.update()
                self.editor.save_file()

            self.highlight_items.clear()
            self.start_pos = None
            self.start_word_idx = -1
            self.render_page()

        elif effective_mode == "postit":
            if not self.start_pos: return
            sel_color = self.tools.current_color
            bg_hex, pdf_col = self.tools.annotation_colors.get(sel_color, settings.ANNOTATION_COLORS["Giallo"])

            postit = PostItItem("", self.start_pos.x(), self.start_pos.y(), bg_color=bg_hex, pdf_color=pdf_col)
            postit.setScale(self.zoom / 2)
            self.scene_obj.addItem(postit)
            postit.text_item.setFocus()
            self.editor.save_file()
            self.start_pos = None


    def is_editing_postit(self) -> bool:
        item = self.scene_obj.focusItem()
        return bool(self.scene_obj.hasFocus() and item and item.data(100) == "postit_text")

    def postit_records(self) -> list[dict[str, Any]]:
        records = []
        for item in self.scene_obj.items():
            if isinstance(item, PostItItem):
                point = item.sceneBoundingRect().center()
                records.append({"id": id(item), "page": self.current_page_num,
                    "point": (point.x() / self.zoom, point.y() / self.zoom), "title": item.title,
                    "text": item.text_item.toPlainText(), "color": item.pdf_color})
        return records
