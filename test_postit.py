import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent
import app

a = QApplication(sys.argv)
doc = app.fitz.open()
doc.insert_page(-1)
doc.save("test.pdf")
doc.close()

mw = app.MainWindow()
mw.viewer.pdf_doc = app.fitz.open("test.pdf")
mw.viewer.render_page()

# Simulate post-it click
mw.viewer.mode = "postit"
press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
mw.viewer.mousePressEvent(press)
release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
mw.viewer.mouseReleaseEvent(release)
print("Items in scene:", len(mw.viewer.scene_obj.items()))
import os
os.remove("test.pdf")
