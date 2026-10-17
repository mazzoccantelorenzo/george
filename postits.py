from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPen
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsTextItem, QInputDialog

from postit_text import PostItTextItem


class PostItResizeHandle(QGraphicsRectItem):
    def __init__(self, postit: "PostItItem") -> None:
        super().__init__(0, 0, 14, 14, postit)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Trascina per ridimensionare il post-it")
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(1)
        self.start_pos = QPointF()
        self.start_rect = QRectF()

    def paint(self, painter: Any, option: Any, widget: Any = None) -> None:
        painter.setPen(QPen(QColor("#777777"), 1.2))
        for offset in (4, 8):
            painter.drawLine(QPointF(offset, 12), QPointF(12, offset))

    def mousePressEvent(self, event: Any) -> None:
        postit = cast(PostItItem, self.parentItem())
        scene = self.scene()
        if scene and scene.views():
            cast(Any, scene.views()[0]).editor.save_file()
        self.start_pos = postit.mapFromScene(event.scenePos())
        self.start_rect = QRectF(postit.rect())
        postit.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event: Any) -> None:
        postit = cast(PostItItem, self.parentItem())
        delta = postit.mapFromScene(event.scenePos()) - self.start_pos
        postit.set_size(self.start_rect.width() + delta.x(), self.start_rect.height() + delta.y())
        event.accept()

    def mouseReleaseEvent(self, event: Any) -> None:
        scene = self.scene()
        if scene and scene.views():
            cast(Any, scene.views()[0]).editor.save_file()
        event.accept()


class PostItItem(QGraphicsRectItem):
    MIN_WIDTH = 120.0
    MIN_HEIGHT = 74.0

    def __init__(self, text: str, x: float, y: float, bg_color: str = "#fceea7", pdf_color: tuple[float, float, float] = (0.98, 0.93, 0.65), width: float = 180, height: float = 74, title: str = "Post-it") -> None:
        super().__init__(0, 0, width, height)
        self.setPos(x, y)
        self.pdf_color = pdf_color
        self.bg_color = bg_color
        self.preferred_height = height
        self.title = title.strip() or "Post-it"

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
        self.title_item = QGraphicsSimpleTextItem(self.header)
        self.title_item.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.Bold))
        self.title_item.setBrush(QBrush(QColor("#555555")))
        self.title_item.setPos(7, 5)
        self.title_item.setToolTip("Doppio clic per rinominare il post-it")
        self.title_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

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
        self.text_item = PostItTextItem(text, self)
        self.text_item.setFont(QFont(".AppleSystemUIFont", 13))
        self.text_item.setDefaultTextColor(QColor("black"))
        self.text_item.setTextWidth(170)
        self.text_item.setPos(5, 24)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_item.setCursor(Qt.CursorShape.IBeamCursor)

        self.setData(100, "postit")
        self.text_item.setData(100, "postit_text")
        self.resize_handle = PostItResizeHandle(self)
        doc = self.text_item.document()
        if doc:
            doc.contentsChanged.connect(self.update_rect)
        self.set_size(width, height)

    def mousePressEvent(self, event: Any) -> None:
        # Called by Qt when PostItItem itself is the top hit.
        # If handle_click doesn't consume the event, fall through to super()
        # so Qt's ItemIsMovable drag mechanism activates.
        if not self.handle_click(event.scenePos()):
            scene = self.scene()
            if scene and scene.views():
                cast(Any, scene.views()[0]).editor.save_file()
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and scene.views():
            cast(Any, scene.views()[0]).editor.save_file()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if self.title_item.sceneBoundingRect().contains(event.scenePos()):
            self.rename()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def rename(self) -> None:
        scene = self.scene()
        if scene is None or not scene.views():
            return
        viewer = cast(Any, scene.views()[0])
        title, accepted = QInputDialog.getText(viewer.window(), "Nome del post-it", "Nome:", text=self.title)
        if not accepted or not title.strip() or title.strip() == self.title:
            return
        viewer.editor.save_file()
        self.title = title.strip()
        self.update_title()
        viewer.editor.save_file()

    def update_title(self) -> None:
        metrics = QFontMetricsF(self.title_item.font())
        self.title_item.setText(metrics.elidedText(self.title, Qt.TextElideMode.ElideRight, self.rect().width() - 62))

    def handle_click(self, scene_pos: Any) -> bool:
        """Handle a click at scene_pos. Returns True if consumed, False to let drag proceed."""

        # Close btn
        if self.close_btn.sceneBoundingRect().contains(scene_pos):
            scene = self.scene()
            if scene:
                cast(Any, scene.views()[0]).editor.save_file()
                self.remove_from_scene()
                if hasattr(scene.views()[0], "editor"):
                    cast(Any, scene.views()[0]).editor.save_file()
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
                    scene = self.scene()
                    if scene and scene.views():
                        cast(Any, scene.views()[0]).editor.save_file()
                    self.set_color(hex_code, pdf_c)
                    self.palette.hide()
                    scene = self.scene()
                    if scene and hasattr(scene.views()[0], "editor"):
                        cast(Any, scene.views()[0]).editor.save_file()
                    return True

        # Plain click on body/header → let drag proceed
        return False

    def remove_from_scene(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        doc = self.text_item.document()
        if doc:
            doc.contentsChanged.disconnect(self.update_rect)
        scene.removeItem(self)
        # The click handler and Qt renderer may still reference these children.
        QTimer.singleShot(0, lambda: sip.delete(self))

    def set_color(self, hex_code: str, pdf_c: tuple[float, float, float]) -> None:
        self.bg_color = hex_code
        self.pdf_color = pdf_c
        self.setBrush(QBrush(QColor(self.bg_color)))
        self.setPen(QPen(QColor(self.bg_color).darker(110), 1))
        self.header.setBrush(QBrush(QColor(self.bg_color).darker(105)))

    def set_size(self, width: float, height: float) -> None:
        width = max(self.MIN_WIDTH, width)
        self.preferred_height = max(self.MIN_HEIGHT, height)
        self.setRect(0, 0, width, self.preferred_height)
        self.header.setRect(0, 0, width, 24)
        self.close_btn.setPos(width - 20, -2)
        self.dots_btn.setPos(width - 45, -2)
        self.update_title()
        self.text_item.setTextWidth(width - 10)
        self.update_rect()

    def update_rect(self) -> None:
        doc = self.text_item.document()
        height = max(self.preferred_height, float(doc.size().height() if doc else 0.0) + 34)
        self.setRect(0, 0, self.rect().width(), height)
        self.resize_handle.setPos(self.rect().width() - 16, height - 16)
