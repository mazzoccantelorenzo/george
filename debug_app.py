from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
import sys
import app

class DebugFilter:
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
                print(f"Global Filter: {event.type()} on {obj}")
        return False

_app = QApplication(sys.argv)
a = app.MainWindow()
f = DebugFilter()
_app.installEventFilter(f)
