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

    def _make_pdf(self, path: str) -> None:
        """Helper: write a minimal single-page PDF to disk."""
        doc = fitz.open()
        doc.insert_page(-1, text="test page")
        doc.save(path)
        doc.close()

    def test_07_postit_persists_across_save_reload(self) -> None:
        """PostIt baked to PDF on save and resurrected as live widget on render_page."""
        tmp = "/tmp/test_07_persist.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = george_app.PostItItem("Hello George", 50, 50)
        self.window.viewer.scene_obj.addItem(postit)
        self.window.save_file()

        # PostIt must still be visible in the scene after save (not removed)
        live = [it for it in self.window.viewer.scene_obj.items()
                if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(live), 1, "PostIt sparito dopo save_file!")

        # Annot must be baked into the PDF on disk.
        # IMPORTANT: PyMuPDF's annot.type is a lazy C++ property that crashes with
        # "annotation not bound to any page" if the Page object is GC'd before access.
        # We must hold an explicit reference to the page while iterating annots.
        doc_check = fitz.open(tmp)
        page_check = doc_check.load_page(0)           # keep alive
        annot_types = [a.type for a in page_check.annots()]  # eager read while page lives
        doc_check.close()
        self.assertEqual(len(annot_types), 1, "FreeText annot non trovata nel PDF!")
        self.assertEqual(annot_types[0][0], fitz.PDF_ANNOT_FREE_TEXT)

        # render_page deve risucchiare l'annot e ricreare il PostItItem
        self.window.viewer.render_page()

        page_fresh = self.window.viewer.pdf_doc[0]
        self.assertEqual(list(page_fresh.annots()), [],
                         "L'annot non è stata rimossa dal PDF in memoria dopo render_page!")

        reloaded = [it for it in self.window.viewer.scene_obj.items()
                    if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(reloaded), 1, "PostIt non ricaricato nella scena!")
        self.assertEqual(reloaded[0].text_item.toPlainText(), "Hello George",
                         f"Testo errato: {reloaded[0].text_item.toPlainText()!r}")

        import os
        os.remove(tmp)

    def test_08_postit_close_button_removes_item(self) -> None:
        """Clicking the × on a PostIt removes it from the scene."""
        tmp = "/tmp/test_08_close.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = george_app.PostItItem("Delete me", 50, 50)
        self.window.viewer.scene_obj.addItem(postit)

        before = [it for it in self.window.viewer.scene_obj.items()
                  if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(before), 1)

        class MockEvent:
            def __init__(self, sp: "QPointF") -> None:
                self._sp = sp
            def scenePos(self) -> "QPointF":
                return self._sp
            def pos(self) -> "QPointF":
                return self._sp
            def accept(self) -> None:
                pass

        postit.mousePressEvent(MockEvent(postit.close_btn.sceneBoundingRect().center()))  # type: ignore[arg-type]

        after = [it for it in self.window.viewer.scene_obj.items()
                 if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(after), 0, "PostIt non rimosso dopo click sulla ×!")

        import os
        os.remove(tmp)

    def test_09_postit_color_change(self) -> None:
        """Clicking a palette color updates the PostIt background color."""
        tmp = "/tmp/test_09_color.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = george_app.PostItItem("Color me", 50, 50, bg_color="#fceea7")
        self.window.viewer.scene_obj.addItem(postit)
        self.assertEqual(postit.bg_color, "#fceea7")

        # Show the palette then click the Verde button (index 1)
        postit.palette.show()
        verde_btn = postit.color_btns[1]

        class MockEvent:
            def __init__(self, sp: "QPointF") -> None:
                self._sp = sp
            def scenePos(self) -> "QPointF":
                return self._sp
            def pos(self) -> "QPointF":
                return self._sp
            def accept(self) -> None:
                pass

        postit.mousePressEvent(MockEvent(verde_btn.sceneBoundingRect().center()))  # type: ignore[arg-type]

        self.assertEqual(postit.bg_color, "#b5f5b5", "Colore non aggiornato dopo click sul pallino Verde!")
        self.assertFalse(postit.palette.isVisible(), "Palette rimasta aperta dopo selezione colore!")

        import os
        os.remove(tmp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
