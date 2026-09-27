
import json
import os
import sys
import traceback
from typing import Any, cast, Optional

import fitz


def global_exception_handler(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    err_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("CRASH INTERCETTATO:", err_msg)
    QMessageBox.critical(None, "Errore Imprevisto (Crash Evitato)", f"Qualcosa è andato storto:\n{err_msg}")
sys.excepthook = global_exception_handler

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFileSystemModel,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

DARK_THEME = """
QMainWindow {
    background-color: #1e1e1e;
}
QTreeView {
    background-color: #252525;
    color: #d4d4d4;
    border: none;
    outline: none;
    font-size: 13px;
}
QTreeView::item {
    padding: 6px;
}
QTreeView::item:hover {
    background-color: #2a2d2e;
}
QTreeView::item:selected {
    background-color: #37373d;
    color: #ffffff;
}
QSplitter::handle {
    background-color: #1e1e1e;
}
QWidget#Toolbar {
    background-color: #2d2d2d;
    border-bottom: 1px solid #1a1a1a;
}
QPushButton {
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4a4a4a;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #2d2d2d;
}
QComboBox {
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #555555;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
    font-weight: bold;
}
QComboBox::drop-down {
    border: none;
}
QComboBox:hover {
    background-color: #4a4a4a;
}
"""

def get_resource_path(relative_path: str) -> str:
    try:
        base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_DIR = os.path.expanduser("~/.george_config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "keys.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "recent_vaults.json")
APP_VERSION = "v12.0"

if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"next_page": "Right", "prev_page": "Left", "mode_highlight": "H", "mode_postit": "P", "save": "S"}, f, indent=4)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

with open(CONFIG_FILE, "r") as f:
    key_config = json.load(f)

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
        self.setWindowTitle(f"George {APP_VERSION} - Vaults")
        self.setFixedSize(700, 480)
        self.setStyleSheet("background-color: #1e1e1e; color: #e0e0e0;")
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)
        
        left_panel = QVBoxLayout()
        header = QLabel(f"George {APP_VERSION}")
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
        
        left_panel.addWidget(header)
        left_panel.addSpacing(15)
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
        
        right_panel.addSpacing(40)
        right_panel.addWidget(icon_label)
        right_panel.addSpacing(40)
        right_panel.addWidget(btn_open)
        
        main_layout.addLayout(left_panel, 60)
        main_layout.addSpacing(25)
        main_layout.addLayout(right_panel, 40)
        
        self.setLayout(main_layout)
        self.selected_path: Optional[str] = None
        
    def load_recent_vaults(self) -> None:
        try:
            with open(HISTORY_FILE, "r") as f:
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
            with open(HISTORY_FILE, "r") as f:
                recent = json.load(f)
        except Exception:
            recent = []
            
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]
        
        with open(HISTORY_FILE, "w") as f:
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

class PostItItem(QGraphicsRectItem):
    def __init__(self, text: str, x: float, y: float, bg_color: str = "#fceea7", pdf_color: tuple[float, float, float] = (0.98, 0.93, 0.65)) -> None:
        super().__init__(0, 0, 180, 70)
        self.setPos(x, y)
        self.pdf_color = pdf_color
        self.bg_color = bg_color

        self.setBrush(QBrush(QColor(bg_color)))
        self.setPen(QPen(QColor(bg_color).darker(110), 1))
        self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        # Header (24px) — cursore a croce frecce per indicare che è trascinabile
        self.header = QGraphicsRectItem(0, 0, 180, 24, self)
        self.header.setBrush(QBrush(QColor(bg_color).darker(108)))
        self.header.setPen(QPen(Qt.PenStyle.NoPen))
        self.header.setCursor(Qt.CursorShape.SizeAllCursor)   # indica drag
        self.header.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        # Close btn  ×  — in alto a destra
        self.close_btn = QGraphicsTextItem("×", self.header)
        font_btn = QFont(".AppleSystemUIFont", 15, QFont.Weight.Bold)
        self.close_btn.setFont(font_btn)
        self.close_btn.setDefaultTextColor(QColor("#666666"))
        self.close_btn.setPos(160, -2)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        # Dots btn  ⋯  — a sinistra della ×
        self.dots_btn = QGraphicsTextItem("⋯", self.header)
        self.dots_btn.setFont(font_btn)
        self.dots_btn.setDefaultTextColor(QColor("#666666"))
        self.dots_btn.setPos(135, -2)
        self.dots_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dots_btn.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        # Color Palette — posizionata SOPRA il post-it (Y negativa) per non coprire il testo
        PALETTE_H = 34
        self.palette = QGraphicsRectItem(0, -(PALETTE_H + 4), 180, PALETTE_H, self)
        self.palette.setBrush(QBrush(QColor("#2a2a2a")))
        self.palette.setPen(QPen(QColor("#555555"), 1))
        self.palette.setZValue(20)
        self.palette.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.palette.hide()

        colors = [
            ("Giallo",  "#fceea7", (0.98, 0.93, 0.65)),
            ("Verde",   "#b5f5b5", (0.71, 0.96, 0.71)),
            ("Rosa",    "#f5b5f5", (0.96, 0.71, 0.96)),
            ("Azzurro", "#b5dcf5", (0.71, 0.86, 0.96))
        ]
        self.color_btns = []
        cx = 15
        for _name, hex_code, pdf_c in colors:
            btn = QGraphicsEllipseItem(cx, 7, 22, 22, self.palette)
            btn.setBrush(QBrush(QColor(hex_code)))
            btn.setPen(QPen(QColor("#888888"), 1))
            btn.setData(101, (hex_code, pdf_c))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.color_btns.append(btn)
            cx += 40

        # Text area
        self.text_item = QGraphicsTextItem(text, self)
        self.text_item.setFont(QFont(".AppleSystemUIFont", 13))
        self.text_item.setDefaultTextColor(QColor("black"))
        self.text_item.setTextWidth(170)
        self.text_item.setPos(5, 24)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_item.setCursor(Qt.CursorShape.IBeamCursor)

        self.setData(100, "postit")
        self.text_item.setData(100, "postit_text")
        doc = self.text_item.document()
        if doc:
            doc.contentsChanged.connect(self.update_rect)

    def mousePressEvent(self, event: Any) -> None:
        # Called by Qt when PostItItem itself is the top hit.
        # If handle_click doesn't consume the event, fall through to super()
        # so Qt's ItemIsMovable drag mechanism activates.
        if not self.handle_click(event.scenePos()):
            super().mousePressEvent(event)

    def handle_click(self, scene_pos: Any) -> bool:
        """Handle a click at scene_pos. Returns True if consumed, False to let drag proceed."""

        # Close btn
        if self.close_btn.sceneBoundingRect().contains(scene_pos):
            scene = self.scene()
            if scene:
                scene.removeItem(self)
                if hasattr(scene.views()[0], "main_window"):
                    cast(Any, scene.views()[0]).main_window.save_file()
            return True

        # Dots btn → toggle palette
        if self.dots_btn.sceneBoundingRect().contains(scene_pos):
            self.palette.setVisible(not self.palette.isVisible())
            return True

        # Color palette btns
        if self.palette.isVisible():
            for btn in self.color_btns:
                if btn.sceneBoundingRect().contains(scene_pos):
                    hex_code, pdf_c = btn.data(101)
                    self.set_color(hex_code, pdf_c)
                    self.palette.hide()
                    scene = self.scene()
                    if scene and hasattr(scene.views()[0], "main_window"):
                        cast(Any, scene.views()[0]).main_window.save_file()
                    return True

        # Plain click on body/header → let drag proceed
        return False

    def set_color(self, hex_code: str, pdf_c: tuple[float, float, float]) -> None:
        self.bg_color = hex_code
        self.pdf_color = pdf_c
        self.setBrush(QBrush(QColor(self.bg_color)))
        self.setPen(QPen(QColor(self.bg_color).darker(110), 1))
        self.header.setBrush(QBrush(QColor(self.bg_color).darker(105)))

    def update_rect(self) -> None:
        doc = self.text_item.document()
        h = max(50.0, float(doc.size().height() if doc else 0.0) + 10)
        # L'altezza totale include l'header da 24px
        self.setRect(0, 0, 180, h + 24)

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
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.pdf_doc = None
        self.current_page_num = 0
        self.zoom = 2.0
        self.mode = "highlight"
        
        
        self.start_pos = None
        self.current_rect_item = None
        
        self.words = []
        self.start_word_idx = -1
        self.highlight_items = []
        
        self.btn_prev = FloatingButton("‹", self)
        self.btn_next = FloatingButton("›", self)
        self.btn_prev.clicked.connect(self.main_window.prev_page)
        self.btn_next.clicked.connect(self.main_window.next_page)
        self.btn_prev.hide()
        self.btn_next.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_prev.move(10, (self.height() - self.btn_prev.height()) // 2)
        self.btn_next.move(self.width() - self.btn_next.width() - 30, (self.height() - self.btn_next.height()) // 2)

    ZOOM_MIN: float = 0.5
    ZOOM_MAX: float = 5.0
    ZOOM_STEP: float = 0.1

    def zoom_by(self, delta: float) -> None:
        """Change zoom by delta (e.g. +0.1 or -0.1), clamp, re-render."""
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom + delta))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
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

    def load_pdf(self, path: str) -> None:
        self.pdf_doc = fitz.open(path)
        self.current_page_num = 0
        self.btn_prev.show()
        self.btn_next.show()
        self.render_page()

    def render_page(self) -> None:
        if not self.pdf_doc: return
        self.scene_obj.clear()
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
            hex_color = f"#{int(pdf_c[0]*255):02x}{int(pdf_c[1]*255):02x}{int(pdf_c[2]*255):02x}"
            x = p["rect"].x0 * self.zoom
            y = (p["rect"].y0 * self.zoom) - 24
            postit = PostItItem(p["text"], x, y, bg_color=hex_color, pdf_color=pdf_c)
            self.scene_obj.addItem(postit)

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
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            focus_item = self.scene_obj.focusItem()
            if focus_item and hasattr(focus_item, "textInteractionFlags"):
                super().keyPressEvent(event)
                return
                
            # Altrimenti cancella i post-it selezionati (bordo esterno cliccato)
            for item in self.scene_obj.selectedItems():
                if item.data(100) == "postit":
                    self.scene_obj.removeItem(item)
                    
        super().keyPressEvent(event)

    def get_effective_mode(self) -> str:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        is_cmd = bool((modifiers & Qt.KeyboardModifier.ControlModifier) or (modifiers & Qt.KeyboardModifier.MetaModifier))
        return "postit" if is_cmd else self.mode

    def mousePressEvent(self, event: Any) -> None:
        if not self.pdf_doc: return
        pos = self.mapToScene(event.pos())
        item = self.scene_obj.itemAt(pos, self.transform())

        if self.mode == "eraser":
            items_at_pos = self.scene_obj.items(pos, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, self.transform())
            deleted = False
            for it in items_at_pos:
                if it.data(100) == "postit":
                    self.scene_obj.removeItem(it)
                    deleted = True
                    break
                elif it.data(100) == "postit_text":
                    self.scene_obj.removeItem(it.parentItem())
                    deleted = True
                    break
            
            if deleted:
                self.main_window.save_file()
                return
                
            p = fitz.Point(pos.x() / self.zoom, pos.y() / self.zoom)
            page = cast(Any, self.pdf_doc)[self.current_page_num]
            if page.first_annot:
                for annot in page.annots():
                    if annot.rect.contains(p):
                        page.delete_annot(annot)
                        self.main_window.save_file()
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
        
        self.start_pos = pos
        if self.get_effective_mode() == "highlight":
            self.start_word_idx = self.get_word_index_at(pos)
        else:
            self.start_word_idx = -1

    def mouseMoveEvent(self, event: Any) -> None:
        super().mouseMoveEvent(event)
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
                    r_item.setBrush(QBrush(QColor(255, 255, 0, 100)))
                    r_item.setPen(QPen(Qt.PenStyle.NoPen))
                    self.scene_obj.addItem(r_item)
                    self.highlight_items.append(r_item)
                    
        

    def mouseReleaseEvent(self, event: Any) -> None:
        super().mouseReleaseEvent(event)
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
                annot.update()
                self.main_window.save_file()
                
            self.highlight_items.clear()  # FIX CRASH: Libera le reference Python prima che render_page() distrugga la scena C++
            self.start_pos = None
            self.start_word_idx = -1
            self.render_page()
            
        elif effective_mode == "postit":
            if not self.start_pos: return
            color_map = {
                "Giallo": ("#fceea7", (0.98, 0.93, 0.65)),
                "Verde": ("#b5f5b5", (0.71, 0.96, 0.71)),
                "Rosa": ("#f5b5f5", (0.96, 0.71, 0.96)),
                "Azzurro": ("#b5dcf5", (0.71, 0.86, 0.96))
            }
            sel_color = getattr(self.main_window, "current_color", "Giallo")
            bg_hex, pdf_col = color_map.get(sel_color, color_map["Giallo"])
            
            postit = PostItItem("", self.start_pos.x(), self.start_pos.y(), bg_color=bg_hex, pdf_color=pdf_col)
            self.scene_obj.addItem(postit)
            postit.text_item.setFocus()
            self.start_pos = None

class MainWindow(QMainWindow):
    def __init__(self, root_path: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"George {APP_VERSION}")
        self.resize(1200, 800)
        self.setStyleSheet(DARK_THEME)
        
        self.viewer = PDFViewer(self)
        self.current_color = "Giallo"
        
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(root_path if root_path else "")
        self.sidebar = QTreeView()
        self.sidebar.setModel(self.file_model)
        self.sidebar.setRootIndex(self.file_model.index(root_path if root_path else ""))
        self.sidebar.setColumnWidth(0, 200)
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAlternatingRowColors(False)
        for i in range(1, 4): self.sidebar.hideColumn(i)
        self.sidebar.doubleClicked.connect(self.open_file)
        
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("Toolbar")
        toolbar_widget.setFixedHeight(40)
        top_layout = QHBoxLayout(toolbar_widget)
        top_layout.setContentsMargins(10, 4, 10, 4)
        
        btn_save = QPushButton(QIcon(get_resource_path("icons/save.svg")), "")
        btn_save.setIconSize(QSize(16, 16))
        btn_save.clicked.connect(self.save_file)
        btn_save.setStyleSheet("background-color: #7a5cfa; border-color: #7a5cfa; color: white;")
        
        btn_help = QPushButton(QIcon(get_resource_path("icons/info.svg")), "")
        btn_help.setIconSize(QSize(16, 16))
        btn_help.clicked.connect(self.show_tutorial)
        btn_help.setToolTip("Tutorial & Info")
        
        top_layout.addWidget(btn_save)
        top_layout.addSpacing(10)
        top_layout.addWidget(btn_help)
        top_layout.addStretch()
        
        # Right Sidebar for tools
        right_toolbar = QWidget()
        right_toolbar.setFixedWidth(60)
        right_toolbar.setStyleSheet("background-color: #252525; border-left: 1px solid #1a1a1a;")
        rt_layout = QVBoxLayout(right_toolbar)
        rt_layout.setContentsMargins(5, 15, 5, 15)
        rt_layout.setSpacing(15)
        
        tool_css = """
            QPushButton { border: none; border-radius: 6px; padding: 8px; }
            QPushButton:checked { background-color: #3a3a3a; }
            QPushButton:hover { background-color: #444444; }
        """
        
        self.btn_group = QButtonGroup()
        
        self.radio_high = QPushButton(QIcon(get_resource_path("icons/highlighter.svg")), "")
        self.radio_high.setIconSize(QSize(22, 22))
        self.radio_high.setCheckable(True)
        self.radio_high.setChecked(True)
        self.radio_high.setStyleSheet(tool_css)
        self.radio_high.setToolTip("Evidenziatore (H)")
        
        self.radio_post = QPushButton(QIcon(get_resource_path("icons/sticky_note.svg")), "")
        self.radio_post.setIconSize(QSize(22, 22))
        self.radio_post.setCheckable(True)
        self.radio_post.setStyleSheet(tool_css)
        self.radio_post.setToolTip("Post-it (P)\nTieni premuto Cmd/Ctrl + Click ovunque!")
        
        self.radio_erase = QPushButton(QIcon(get_resource_path("icons/eraser.svg")), "")
        self.radio_erase.setIconSize(QSize(22, 22))
        self.radio_erase.setCheckable(True)
        self.radio_erase.setStyleSheet(tool_css)
        self.radio_erase.setToolTip("Gomma (E)")
        
        self.btn_group.addButton(self.radio_high)
        self.btn_group.addButton(self.radio_post)
        self.btn_group.addButton(self.radio_erase)
        
        self.radio_high.toggled.connect(self.change_mode)
        self.radio_post.toggled.connect(self.change_mode)
        self.radio_erase.toggled.connect(self.change_mode)
        
        self.color_buttons: dict[str, tuple[QPushButton, str]] = {}
        self.current_color = "Giallo"
        
        def select_color(col_name: str) -> None:
            self.current_color = col_name
            for name, (btn, hex_code) in self.color_buttons.items():
                if name == col_name:
                    btn.setStyleSheet(f"background-color: {hex_code}; border-radius: 12px; border: 3px solid #ffffff;")
                else:
                    btn.setStyleSheet(f"background-color: {hex_code}; border-radius: 12px; border: 1px solid #000000;")
                    
        def make_color_btn(col_name: str, hex_code: str) -> QPushButton:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.clicked.connect(lambda checked=False, c=col_name: select_color(c))
            self.color_buttons[col_name] = (btn, hex_code)
            return btn
            
        color_layout = QVBoxLayout()
        color_layout.setSpacing(8)
        color_layout.addWidget(make_color_btn("Giallo", "#fceea7"), 0, Qt.AlignmentFlag.AlignHCenter)
        color_layout.addWidget(make_color_btn("Verde", "#b5f5b5"), 0, Qt.AlignmentFlag.AlignHCenter)
        color_layout.addWidget(make_color_btn("Rosa", "#f5b5f5"), 0, Qt.AlignmentFlag.AlignHCenter)
        color_layout.addWidget(make_color_btn("Azzurro", "#b5dcf5"), 0, Qt.AlignmentFlag.AlignHCenter)
        select_color("Giallo")
        
        rt_layout.addWidget(self.radio_erase)
        rt_layout.addWidget(self.radio_high)
        rt_layout.addWidget(self.radio_post)
        rt_layout.addLayout(color_layout)
        rt_layout.addStretch()
        
        pdf_and_rt_layout = QHBoxLayout()
        pdf_and_rt_layout.setContentsMargins(0, 0, 0, 0)
        pdf_and_rt_layout.setSpacing(0)
        pdf_and_rt_layout.addWidget(self.viewer)
        pdf_and_rt_layout.addWidget(right_toolbar)
        
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
        splitter.addWidget(self.sidebar)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 950])
        
        self.setCentralWidget(splitter)

        def safe_shortcut(btn):
            focus_item = self.viewer.scene_obj.focusItem()
            # Se stiamo scrivendo in un post-it, non attivare gli shortcut a singola lettera!
            if focus_item and hasattr(focus_item, "textInteractionFlags") and focus_item.textInteractionFlags():
                return
            btn.setChecked(True)

        QShortcut(QKeySequence("H"), self).activated.connect(lambda: safe_shortcut(self.radio_high))
        QShortcut(QKeySequence("P"), self).activated.connect(lambda: safe_shortcut(self.radio_post))
        QShortcut(QKeySequence("E"), self).activated.connect(lambda: safe_shortcut(self.radio_erase))
        QShortcut(QKeySequence("Right"), self).activated.connect(self.next_page)
        QShortcut(QKeySequence("Left"), self).activated.connect(self.prev_page)
        
        # Save è sempre Ctrl+S / Cmd+S per non interferire mai con la scrittura
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_file)

        # Zoom in/out: Cmd++ e Cmd+- (+ e = sono sullo stesso tasto fisico)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.viewer.zoom_by(self.viewer.ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.viewer.zoom_by(self.viewer.ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.viewer.zoom_by(-self.viewer.ZOOM_STEP))

        self.change_mode()
        from PyQt6.QtWidgets import QApplication
        app_inst = QApplication.instance()
        if app_inst: app_inst.installEventFilter(self)


    def eventFilter(self, obj: Any, event: Any) -> bool:
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtWidgets import QApplication
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
                # KeyPress of Cmd/Ctrl = Cmd is now held.
                # KeyRelease of Cmd/Ctrl = Cmd is now released.
                # No need to check modifiers() — the key identity is the signal.
                is_cmd = (event.type() == QEvent.Type.KeyPress)

                if is_cmd:
                    from PyQt6.QtGui import QCursor, QIcon
                    icon = QIcon(get_resource_path("icons/sticky_note.svg"))
                    # setOverrideCursor beats every item-level cursor (IBeam, Arrow, etc.)
                    QApplication.setOverrideCursor(QCursor(icon.pixmap(28, 28), 0, 0))
                else:
                    QApplication.restoreOverrideCursor()
                    self.radio_high.setChecked(True)
                    self.change_mode()
        return super().eventFilter(obj, event)

    def change_mode(self) -> None:
        if self.radio_high.isChecked():
            self.viewer.mode = "highlight"
            self.viewer.setCursor(Qt.CursorShape.IBeamCursor)
        elif self.radio_post.isChecked():
            self.viewer.mode = "postit"
            self.viewer.setCursor(Qt.CursorShape.ArrowCursor)
        elif self.radio_erase.isChecked():
            self.viewer.mode = "eraser"
            icon = QIcon(get_resource_path("icons/eraser.svg"))
            self.viewer.setCursor(QCursor(icon.pixmap(22, 22), 0, 22))

    def open_file(self, index: Any) -> None:
        path = self.file_model.filePath(index)
        if path.lower().endswith(".pdf"):
            self.save_file()
            self.viewer.load_pdf(path)

    def save_file(self) -> None:
        if not self.viewer.pdf_doc: return
        page = self.viewer.pdf_doc[self.viewer.current_page_num]
        # Elimina i FreeText correnti per evitare duplicati quando rifacciamo il bake
        if page.first_annot:
            annot = page.first_annot
            while annot:
                next_annot = annot.next
                if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                    page.delete_annot(annot)
                annot = next_annot
        
        # Bake live items
        for item in self.viewer.scene_obj.items():
            if getattr(item, "data", lambda x: None)(100) == "postit":
                # Escludiamo l'header (24px) dall'annotazione del PDF, così il testo non shifta in alto
                header_offset = 24 / self.viewer.zoom
                x, y = item.x() / self.viewer.zoom, item.y() / self.viewer.zoom
                w, h = cast(Any, item).rect().width() / self.viewer.zoom, (cast(Any, item).rect().height() - 24) / self.viewer.zoom
                rect = fitz.Rect(x, y + header_offset, x+w, y+header_offset+h)
                text = cast(Any, item).text_item.toPlainText()
                
                annot = page.add_freetext_annot(rect, text, fontsize=12, text_color=(0,0,0), fill_color=cast(Any, item).pdf_color)
                annot.update()
                # Salvataggio sicuro tramite file temporaneo per evitare corruzione della memoria
        try:
            doc = self.viewer.pdf_doc
            path = doc.name
            temp_path = path + ".tmp.pdf"
            # Un full save elimina il rischio di corrompere il file originale o l'oggetto in memoria
            doc.save(temp_path, encryption=fitz.PDF_ENCRYPT_KEEP)
            import os
            # Su Mac/Linux possiamo sovrascrivere il file anche se è aperto. L'inode originale viene mantenuto vivo dal SO.
            os.replace(temp_path, path)
        except Exception as e:
            print("Auto-save fallito:", e)


    def show_tutorial(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        msg = "Benvenuto in George v12.0\n\n"
        msg += "📖 STRUMENTI:\n"
        msg += "- Evidenziatore (H): Seleziona il testo per evidenziare.\n"
        msg += "- Post-it (P): Clicca sul PDF per creare un post-it, inizia subito a scrivere.\n"
        msg += "- Gomma (E): Clicca su un post-it o un highlight per cancellarlo.\n\n"
        msg += "💾 SALVATAGGIO:\n"
        msg += "- Auto-Save: Ogni highlight o modifica viene salvata in tempo reale nel PDF originale.\n"
        msg += "- Ctrl+S / Tasto Floppy: Forza il salvataggio manuale dei post-it attivi.\n\n"
        msg += "⌨️ SHORTCUT:\n"
        msg += "- Freccia Destra/Sinistra: Cambia pagina.\n"
        msg += "- Canc/Backspace: Elimina il Post-it selezionato (cliccando sul bordo esterno)."
        QMessageBox.information(self, "Tutorial di George", msg)

    def prev_page(self) -> None:
        if self.viewer.pdf_doc and self.viewer.current_page_num > 0:
            self.viewer.current_page_num -= 1
            self.viewer.render_page()

    def next_page(self) -> None:
        if self.viewer.pdf_doc and self.viewer.current_page_num < len(self.viewer.pdf_doc) - 1:
            self.viewer.current_page_num += 1
            self.viewer.render_page()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont(".AppleSystemUIFont", 13))
    app.setStyle("Fusion")
    selector = VaultSelector()
    if selector.exec():
        window = MainWindow(selector.selected_path)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)
