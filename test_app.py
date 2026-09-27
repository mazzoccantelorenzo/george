import sys
import os
import unittest
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import QPointF, QPoint, Qt

app = QApplication(sys.argv)
import app as george_app

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

if __name__ == '__main__':
    unittest.main(verbosity=2)

    def test_tutorial_shows(self):
        # Simula il click sul bottone help
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            self.window.show_tutorial()
            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            self.assertEqual(args[1], "Tutorial di George")
            self.assertIn("STRUMENTI", args[2])



if __name__ == '__main__':
    unittest.main()
