import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent, QKeyEvent
import fitz
from window import MainWindow

a = QApplication(sys.argv)
doc = fitz.open()
doc.insert_page(-1)
doc.save("test.pdf")
doc.close()

mw = MainWindow()
mw.viewer.pdf_doc = fitz.open("test.pdf")
mw.viewer.render_page()

# Test pure click
mw.viewer.mode = "postit"
press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(50, 50), QPointF(50, 50), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
mw.viewer.mousePressEvent(press)
release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(50, 50), QPointF(50, 50), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
mw.viewer.mouseReleaseEvent(release)
print("Items:", len(mw.viewer.scene_obj.items()))

# Test Cmd+click in highlight mode
mw.viewer.mode = "highlight"
press2 = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(100, 100), QPointF(100, 100), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
# we need to simulate the eventFilter setting is_cmd? no, mouseRelease checks keyboardModifiers, which we can't easily fake in QMouseEvent unless we mock QApplication.keyboardModifiers.
