import sys
import os
import unittest
import json
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtCore import QPointF, QPoint, Qt
import app as george_app
import fitz

# Ensure QApplication exists before tests
_app = QApplication.instance()
if not _app:
    _app = QApplication(sys.argv)

class TestGeorgeApp(unittest.TestCase):
    def setUp(self):
        self.window = george_app.MainWindow()
        
    def test_01_mode_switch(self):
        self.assertEqual(self.window.viewer.mode, "highlight")
        self.window.radio_post.setChecked(True)
        self.assertEqual(self.window.viewer.mode, "postit")
        
    def test_02_pdf_viewer_initialization(self):
        viewer = self.window.viewer
        self.assertIsNone(viewer.pdf_doc)
        self.assertEqual(viewer.current_page_num, 0)
        self.assertEqual(len(viewer.highlight_items), 0)
        
    def test_03_get_word_index_empty(self):
        viewer = self.window.viewer
        viewer.words = []
        idx = viewer.get_word_index_at(QPointF(100, 100))
        self.assertEqual(idx, -1)
        
    def test_04_history_management(self):
        selector = george_app.VaultSelector()
        test_path = "/tmp/test_george_vault"
        os.makedirs(test_path, exist_ok=True)
        selector.save_recent_vault(test_path)
        
        with open(george_app.HISTORY_FILE, "r") as f:
            history = json.load(f)
            self.assertIn(test_path, history)

    def test_05_tutorial_shows(self):
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            self.window.show_tutorial()
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            self.assertEqual(args[1], "Tutorial di George")
            self.assertIn("STRUMENTI", args[2])

    def test_06_render_page_keeps_image_alive(self):
        # Create a dummy pdf
        test_pdf = "test_render.pdf"
        doc = fitz.open()
        doc.insert_page(-1, text="Test page rendering")
        doc.save(test_pdf)
        doc.close()

        self.window.viewer.load_pdf(test_pdf)
        # Verify the pixmap was added to the scene and is not null
        items = self.window.viewer.scene_obj.items()
        self.assertGreater(len(items), 0)
        
        # Ensure it has a valid QPixmap width/height indicating it rendered properly
        pixmap_items = [item for item in items if hasattr(item, "pixmap")]
        self.assertGreater(len(pixmap_items), 0)
        pm = pixmap_items[0].pixmap()
        self.assertFalse(pm.isNull())
        self.assertGreater(pm.width(), 0)
        self.assertGreater(pm.height(), 0)

        os.remove(test_pdf)

if __name__ == '__main__':
    unittest.main(verbosity=2)
