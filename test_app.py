import sys
import os
import unittest
import json
import tempfile
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent, QPixmap, QKeySequence
from PyQt6.QtCore import QPointF, QPoint, QRectF, Qt
import settings
from postits import PostItItem
from vault import VaultSelector
from window import MainWindow
import fitz

# Ensure QApplication exists before tests
_app = QApplication.instance()
if not _app:
    _app = QApplication(sys.argv)

class TestGeorgeApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_dir = tempfile.TemporaryDirectory(prefix="george-tests-config-")
        history = os.path.join(cls.config_dir.name, "history.json")
        with open(history, "w") as f:
            json.dump([], f)
        cls.history_patch = patch.object(settings, "HISTORY_FILE", history)
        cls.history_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.history_patch.stop()
        cls.config_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="george-test-")
        self.color_patch = patch.object(settings, "COLORS_FILE", os.path.join(self.tmp.name, "colors.json"))
        self.color_patch.start()
        self.session_patch = patch.object(settings, "SESSION_FILE", os.path.join(self.tmp.name, "session.json"))
        self.session_patch.start()
        self.bookmark_patch = patch.object(settings, "BOOKMARKS_FILE", os.path.join(self.tmp.name, "bookmarks.json"))
        self.bookmark_patch.start()
        self.chat_patch = patch.object(settings, "CHAT_DIR", os.path.join(self.tmp.name, "chats"))
        self.chat_patch.start()
        self.window = MainWindow(self.tmp.name)

    def tearDown(self):
        if self.window.viewer.pdf_doc:
            self.window.viewer.pdf_doc.close()
            self.window.viewer.pdf_doc = None
        self.window.close()
        self.window.deleteLater()
        from PyQt6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.color_patch.stop()
        self.session_patch.stop()
        self.bookmark_patch.stop()
        self.chat_patch.stop()
        self.tmp.cleanup()
        
    def test_01_mode_switch(self):
        self.assertEqual(self.window.viewer.mode, "highlight")
        self.window.tools.radio_post.setChecked(True)
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
        selector = VaultSelector()
        test_path = "/tmp/test_george_vault"
        os.makedirs(test_path, exist_ok=True)
        selector.save_recent_vault(test_path)
        
        with open(settings.HISTORY_FILE, "r") as f:
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

        postit = PostItItem("Hello George", 50, 50)
        self.window.viewer.scene_obj.addItem(postit)
        self.window.viewer.editor.save_file()

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
        """Clicking the × on a PostIt removes it from the scene and handle_click returns True."""
        tmp = "/tmp/test_08_close.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = PostItItem("Delete me", 50, 50)
        self.window.viewer.scene_obj.addItem(postit)

        before = [it for it in self.window.viewer.scene_obj.items()
                  if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(before), 1)

        consumed = postit.handle_click(postit.close_btn.sceneBoundingRect().center())
        self.assertTrue(consumed, "handle_click should return True for close btn!")

        after = [it for it in self.window.viewer.scene_obj.items()
                 if getattr(it, "data", lambda x: None)(100) == "postit"]
        self.assertEqual(len(after), 0, "PostIt non rimosso dopo click sulla ×!")

        import os
        os.remove(tmp)

    def test_09_postit_color_change(self) -> None:
        """Clicking a palette color updates the PostIt background color and returns True."""
        tmp = "/tmp/test_09_color.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = PostItItem("Color me", 50, 50, bg_color="#fceea7")
        self.window.viewer.scene_obj.addItem(postit)
        self.assertEqual(postit.bg_color, "#fceea7")

        # Show the palette via dots_btn
        consumed_dots = postit.handle_click(postit.dots_btn.sceneBoundingRect().center())
        self.assertTrue(consumed_dots, "Dots btn click should return True!")
        self.assertTrue(postit.palette.isVisible(), "Palette deve essere visibile!")

        # Click Verde
        consumed_color = postit.handle_click(postit.color_btns[1].sceneBoundingRect().center())
        self.assertTrue(consumed_color, "Color btn click should return True!")

        self.assertEqual(postit.bg_color, "#b5f5b5", "Colore non aggiornato dopo click sul pallino Verde!")
        self.assertFalse(postit.palette.isVisible(), "Palette rimasta aperta dopo selezione colore!")

        import os
        os.remove(tmp)

    def test_13_postit_body_click_allows_drag(self) -> None:
        """Clicking the header body (not close/dots/color) returns False so drag can proceed."""
        postit = PostItItem("Move me", 50, 50)
        self.window.viewer.scene_obj.addItem(postit)

        # Click the center of the header (not on any button)
        header_center = postit.header.sceneBoundingRect().center()
        # Make sure we're not on close or dots
        close_rect = postit.close_btn.sceneBoundingRect()
        dots_rect  = postit.dots_btn.sceneBoundingRect()
        self.assertFalse(close_rect.contains(header_center))
        self.assertFalse(dots_rect.contains(header_center))

        consumed = postit.handle_click(header_center)
        self.assertFalse(consumed, "Plain header click should return False so drag is allowed!")

    def test_10_zoom_by_changes_zoom_level(self) -> None:
        """zoom_by increases / decreases self.zoom by ZOOM_STEP and clamps at limits."""
        viewer = self.window.viewer
        initial = viewer.zoom

        viewer.zoom_by(viewer.ZOOM_STEP)
        self.assertAlmostEqual(viewer.zoom, initial + viewer.ZOOM_STEP, places=5)

        viewer.zoom_by(-viewer.ZOOM_STEP)
        self.assertAlmostEqual(viewer.zoom, initial, places=5)

    def test_11_zoom_clamps_at_min_max(self) -> None:
        """zoom_by never goes below ZOOM_MIN or above ZOOM_MAX."""
        viewer = self.window.viewer

        viewer.zoom = viewer.ZOOM_MIN
        viewer.zoom_by(-10.0)  # try to go way below min
        self.assertAlmostEqual(viewer.zoom, viewer.ZOOM_MIN, places=5)

        viewer.zoom = viewer.ZOOM_MAX
        viewer.zoom_by(10.0)  # try to go way above max
        self.assertAlmostEqual(viewer.zoom, viewer.ZOOM_MAX, places=5)

    def test_12_postit_color_change_via_viewer_routing(self) -> None:
        """Clicking a color btn via PDFViewer.mousePressEvent actually changes the PostIt color.

        This is the bug regression test: sub-items (dots_btn, color_btns) are grandchildren
        of PostItItem and were previously invisible to PDFViewer's event routing, so clicking
        the palette did nothing.
        """
        tmp = "/tmp/test_12_routing.pdf"
        self._make_pdf(tmp)
        self.window.viewer.load_pdf(tmp)

        postit = PostItItem("Routing test", 50, 50, bg_color="#fceea7")
        self.window.viewer.scene_obj.addItem(postit)
        self.assertEqual(postit.bg_color, "#fceea7")

        # Step 1 – show palette via dots_btn click routed through PDFViewer
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent

        def send_click(scene_pt: "QPointF") -> None:
            vp_pt = self.window.viewer.mapFromScene(scene_pt)
            ev = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(vp_pt),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            from PyQt6.QtWidgets import QApplication
            QApplication.sendEvent(self.window.viewer.viewport(), ev)

        send_click(postit.dots_btn.sceneBoundingRect().center())
        self.assertTrue(postit.palette.isVisible(),
                        "Palette non si è aperta dopo click sui tre puntini via PDFViewer!")

        # Step 2 – click Verde via PDFViewer
        verde_center = postit.color_btns[1].sceneBoundingRect().center()
        send_click(verde_center)

        self.assertEqual(postit.bg_color, "#b5f5b5",
                         "Il colore del PostIt non è cambiato dopo click via PDFViewer!")
        self.assertFalse(postit.palette.isVisible(),
                         "Palette rimasta aperta dopo click colore via PDFViewer!")

        import os
        os.remove(tmp)


    def test_14_cmd_cursor_is_scoped_and_repeated_events_do_not_leave_it_stuck(self) -> None:
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QApplication

        for _ in range(3):
            press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Meta, Qt.KeyboardModifier.MetaModifier)
            self.window.eventFilter(self.window.viewer.viewport(), press)
        self.assertEqual(self.window.viewer.get_effective_mode(), "postit")
        self.assertFalse(self.window.viewer.viewport().cursor().pixmap().isNull())
        self.assertIsNone(QApplication.overrideCursor())
        release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Meta, Qt.KeyboardModifier.NoModifier)
        self.window.eventFilter(self.window, release)
        self.assertEqual(self.window.viewer.get_effective_mode(), "highlight")
        self.assertEqual(self.window.viewer.viewport().cursor().shape(), Qt.CursorShape.BitmapCursor)
        self.assertIsNone(QApplication.overrideCursor())

    def test_15_modifier_release_preserves_tool_and_lost_focus_resets_temporary_mode(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        self.window.tools.radio_erase.click()
        press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Meta, Qt.KeyboardModifier.MetaModifier)
        self.window.eventFilter(self.window, press)
        self.assertEqual(self.window.viewer.get_effective_mode(), "postit")
        self.window.eventFilter(_app, QEvent(QEvent.Type.ApplicationDeactivate))
        self.assertEqual(self.window.viewer.get_effective_mode(), "eraser")
        self.assertTrue(self.window.tools.radio_erase.isChecked())
        self.window.tools.radio_high.click()
        self.assertEqual(self.window.viewer.viewport().cursor().shape(), Qt.CursorShape.BitmapCursor)

    def test_16_highlight_color_matches_preview_and_saved_pdf(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QColor
        viewer = self.window.viewer
        self.window.show()
        for name, (hex_color, pdf_color) in settings.ANNOTATION_COLORS.items():
            with self.subTest(color=name):
                path = os.path.join(self.tmp.name, name + ".pdf")
                self._make_pdf(path)
                viewer.load_pdf(path)
                _app.processEvents()
                self.window.tools.color_buttons[name][0].click()
                word = viewer.words[0]
                point = viewer.mapFromScene(QPointF(
                    (word[0] + word[2]) * viewer.zoom / 2,
                    (word[1] + word[3]) * viewer.zoom / 2,
                ))
                for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove):
                    event = QMouseEvent(kind, QPointF(point),
                        Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                    QApplication.sendEvent(viewer.viewport(), event)
                self.assertTrue(viewer.highlight_items)
                self.assertEqual(viewer.highlight_items[0].brush().color().name(), QColor(hex_color).name())
                release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(point),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(viewer.viewport(), release)
                with fitz.open(path) as check:
                    page = check[0]
                    annotations = list(page.annots())
                    self.assertEqual(len(annotations), 1)
                    self.assertEqual(annotations[0].type[0], fitz.PDF_ANNOT_HIGHLIGHT)
                    for actual, expected in zip(annotations[0].colors["stroke"], pdf_color):
                        self.assertAlmostEqual(actual, expected, places=5)

    def test_17_scene_replacement_defers_deletion_and_cancels_selection(self):
        from PyQt6 import sip
        from PyQt6.QtCore import QCoreApplication, QEvent, QRectF
        from PyQt6.QtWidgets import QGraphicsRectItem
        path = os.path.join(self.tmp.name, "scene.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        old_scene = viewer.scene_obj
        preview = QGraphicsRectItem(QRectF(0, 0, 30, 10))
        old_scene.addItem(preview)
        viewer.highlight_items.append(preview)
        viewer.start_pos = QPointF(1, 1)
        viewer.start_word_idx = 0
        viewer.render_page()
        self.assertIsNot(old_scene, viewer.scene_obj)
        self.assertFalse(sip.isdeleted(old_scene))
        self.assertFalse(viewer.highlight_items)
        self.assertIsNone(viewer.start_pos)
        self.assertEqual(viewer.start_word_idx, -1)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(sip.isdeleted(old_scene))
        self.assertTrue(sip.isdeleted(preview))

    def test_18_postit_text_survives_zoom_and_page_navigation(self):
        path = os.path.join(self.tmp.name, "pages.pdf")
        with fitz.open() as doc:
            for _ in range(2):
                doc.insert_page(-1, text="test page")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        note = PostItItem("Keep this note", 100, 100)
        viewer.scene_obj.addItem(note)
        viewer.zoom_by(0.1)
        notes = [item for item in viewer.scene_obj.items() if isinstance(item, PostItItem)]
        self.assertEqual(len(notes), 1)
        notes[0].text_item.setPlainText("Edited after zoom")
        self.window.next_page()
        self.window.prev_page()
        notes = [item for item in viewer.scene_obj.items() if isinstance(item, PostItItem)]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].text_item.toPlainText(), "Edited after zoom")

    def test_19_closing_focused_postit_defers_native_deletion_and_removes_saved_note(self):
        from PyQt6 import sip
        from PyQt6.QtCore import QEvent
        path = os.path.join(self.tmp.name, "deleted.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        self.window.show()
        viewer.load_pdf(path)
        note = PostItItem("Delete this edited note", 100, 100)
        viewer.scene_obj.addItem(note)
        note.text_item.setFocus()
        _app.processEvents()
        note.text_item.setPlainText("Edited while focused")
        self.window.viewer.editor.save_file()
        point = viewer.mapFromScene(note.close_btn.sceneBoundingRect().center())
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(viewer.viewport(), event)
        self.assertIsNone(note.scene())
        self.assertFalse(sip.isdeleted(note))
        with fitz.open(path) as check:
            page = check[0]
            self.assertEqual(list(page.annots()), [])
        _app.processEvents()
        self.assertTrue(sip.isdeleted(note))
        viewer.viewport().repaint()

    def test_20_numeric_shortcuts_and_tool_toggle(self):
        from PyQt6.QtTest import QTest
        self.window.show()
        _app.setActiveWindow(self.window)
        self.window.viewer.setFocus()
        _app.processEvents()
        for key, name in [(Qt.Key.Key_2, "Verde"), (Qt.Key.Key_3, "Rosa"),
                          (Qt.Key.Key_4, "Azzurro"), (Qt.Key.Key_1, "Giallo")]:
            QTest.keyClick(self.window.viewer, key)
            self.assertEqual(self.window.tools.current_color, name)
        QTest.keyClick(self.window.viewer, Qt.Key.Key_E)
        self.assertEqual(self.window.viewer.mode, "pointer")
        self.assertFalse(any(button.isChecked() for button in self.window.tools.btn_group.buttons()))
        self.assertEqual(self.window.viewer.viewport().cursor().shape(), Qt.CursorShape.BitmapCursor)
        QTest.keyClick(self.window.viewer, Qt.Key.Key_E)
        self.assertEqual(self.window.viewer.mode, "highlight")
        QTest.keyClick(self.window.viewer, Qt.Key.Key_Q)
        self.assertEqual(self.window.viewer.mode, "eraser")

    def test_21_shortcuts_do_not_consume_postit_text(self):
        from PyQt6.QtTest import QTest
        self.window.show()
        _app.setActiveWindow(self.window)
        self.window.viewer.setFocus()
        note = PostItItem("", 50, 50)
        self.window.viewer.scene_obj.addItem(note)
        note.text_item.setFocus()
        _app.processEvents()
        QTest.keyClicks(self.window.viewer.viewport(), "1234eqp")
        self.assertEqual(note.text_item.toPlainText(), "1234eqp")
        self.assertEqual(self.window.tools.current_color, "Giallo")
        self.assertEqual(self.window.viewer.mode, "highlight")

    def test_22_custom_color_picker_persists_and_reuses_colors(self):
        from PyQt6.QtGui import QColor
        with patch("tools.QColorDialog.getColor", return_value=QColor("#ff8800")) as picker:
            self.window.tools.add_color_btn.click()
        picker.assert_called_once()
        self.assertEqual(self.window.tools.current_color, "#ff8800")
        self.assertEqual(self.window.tools.color_buttons["#ff8800"][0].text(), "5")
        self.assertEqual(self.window.tools.annotation_colors["#ff8800"][0], "#ff8800")
        with open(settings.COLORS_FILE) as f:
            self.assertEqual(json.load(f), ["#ff8800"])
        with patch("tools.QColorDialog.getColor", return_value=QColor("#ff8800")):
            self.window.tools.add_color_btn.click()
        self.assertEqual(len(self.window.tools.color_buttons), 5)
        other = MainWindow(self.tmp.name)
        try:
            self.assertIn("#ff8800", other.tools.annotation_colors)
            self.assertEqual(other.tools.color_buttons["#ff8800"][0].text(), "5")
        finally:
            other.close()
            other.deleteLater()

    def test_23_cancel_color_picker_keeps_palette_unchanged(self):
        from PyQt6.QtGui import QColor
        with patch("tools.QColorDialog.getColor", return_value=QColor()):
            self.window.tools.add_color_btn.click()
        self.assertEqual(len(self.window.tools.color_buttons), 4)
        self.assertEqual(self.window.tools.current_color, "Giallo")
        self.assertFalse(os.path.exists(settings.COLORS_FILE))

    def test_24_pointer_selects_and_copies_pdf_text_without_annotations(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "select.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima seconda\nterza quarta")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        _app.processEvents()
        QTest.keyClick(viewer, Qt.Key.Key_E)
        with open(path, "rb") as f:
            original = f.read()
        for reverse in (False, True):
            words = (viewer.words[-1], viewer.words[0]) if reverse else (viewer.words[0], viewer.words[-1])
            points = [viewer.mapFromScene(QPointF((w[0] + w[2]) * viewer.zoom / 2,
                (w[1] + w[3]) * viewer.zoom / 2)) for w in words]
            for kind, point, button, buttons in [
                (QEvent.Type.MouseButtonPress, points[0], Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
                (QEvent.Type.MouseMove, points[1], Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
                (QEvent.Type.MouseButtonRelease, points[1], Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
            ]:
                QApplication.sendEvent(viewer.viewport(), QMouseEvent(kind, QPointF(point), button,
                    buttons, Qt.KeyboardModifier.NoModifier))
            self.assertEqual(viewer.selected_text(), "prima seconda\nterza quarta")
            viewer.viewport().repaint()
            _app.clipboard().setText("old clipboard")
            QTest.keySequence(viewer, QKeySequence(QKeySequence.StandardKey.Copy))
            self.assertEqual(_app.clipboard().text(), "prima seconda\nterza quarta")
            self.assertFalse(viewer.highlight_items)
            self.assertEqual(list(viewer.pdf_doc[0].annots()), [])
            with open(path, "rb") as f:
                self.assertEqual(f.read(), original)

    def test_25_pdf_selection_clears_on_blank_click_tool_change_and_zoom(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "clear-selection.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        _app.processEvents()
        QTest.keyClick(viewer, Qt.Key.Key_E)
        word = viewer.words[0]
        point = viewer.mapFromScene(QPointF((word[0] + word[2]) * viewer.zoom / 2,
            (word[1] + word[3]) * viewer.zoom / 2))
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(viewer.selected_text(), "test")
        blank = viewer.mapFromScene(QPointF(400, 400))
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=blank)
        self.assertEqual(viewer.selected_text(), "")
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.keyClick(viewer, Qt.Key.Key_E)
        self.assertIsNone(viewer.text_selection)
        QTest.keyClick(viewer, Qt.Key.Key_E)
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(viewer.selected_text(), "test")
        viewer.zoom_by(0.1)
        self.assertIsNone(viewer.text_selection)
        self.assertEqual(viewer.viewport().cursor().shape(), Qt.CursorShape.BitmapCursor)

    def test_26_copy_in_postit_uses_postit_text(self):
        from PyQt6.QtGui import QTextCursor
        from PyQt6.QtTest import QTest
        viewer = self.window.viewer
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        note = PostItItem("testo nota", 50, 50)
        viewer.scene_obj.addItem(note)
        viewer.words = [(0, 0, 10, 10, "testo PDF", 0, 0, 0)]
        viewer.text_selection = (0, 0)
        note.text_item.setFocus()
        cursor = note.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.text_item.setTextCursor(cursor)
        _app.processEvents()
        QTest.keySequence(viewer.viewport(), QKeySequence(QKeySequence.StandardKey.Copy))
        self.assertEqual(_app.clipboard().text(), "testo nota")

    def test_27_a_d_navigate_pages_and_remain_letters_in_postits(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "navigation.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima pagina")
            doc.insert_page(-1, text="seconda pagina")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        _app.processEvents()
        QTest.keyClick(viewer, Qt.Key.Key_A)
        self.assertEqual(viewer.current_page_num, 0)
        viewer.text_selection = (0, 0)
        QTest.keyClick(viewer, Qt.Key.Key_D)
        self.assertEqual(viewer.current_page_num, 1)
        self.assertIsNone(viewer.text_selection)
        QTest.keyClick(viewer, Qt.Key.Key_D)
        self.assertEqual(viewer.current_page_num, 1)
        QTest.keyClick(viewer, Qt.Key.Key_A)
        self.assertEqual(viewer.current_page_num, 0)
        note = PostItItem("", 50, 50)
        viewer.scene_obj.addItem(note)
        note.text_item.setFocus()
        _app.processEvents()
        QTest.keyClicks(viewer.viewport(), "adAD")
        self.assertEqual(note.text_item.toPlainText(), "adAD")
        self.assertEqual(viewer.current_page_num, 0)

    def test_28_resize_handle_grows_shrinks_and_saves_the_postit(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "resize.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        note = PostItItem("Nota", 200, 200)
        viewer.scene_obj.addItem(note)
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        _app.processEvents()
        viewer.ensureVisible(note)

        for width, height in [(360, 220), (140, 90)]:
            start = note.resize_handle.sceneBoundingRect().center()
            end = start + QPointF(width - note.rect().width(), height - note.rect().height())
            QTest.mousePress(viewer.viewport(), Qt.MouseButton.LeftButton, pos=viewer.mapFromScene(start))
            QTest.mouseMove(viewer.viewport(), viewer.mapFromScene(end))
            QTest.mouseRelease(viewer.viewport(), Qt.MouseButton.LeftButton, pos=viewer.mapFromScene(end))
            self.assertAlmostEqual(note.rect().width(), width)
            self.assertAlmostEqual(note.rect().height(), height)
            self.assertEqual(note.pos(), QPointF(200, 200))
            self.assertEqual(note.header.rect().width(), width)
            self.assertEqual(note.text_item.textWidth(), width - 10)
            self.assertEqual(note.close_btn.pos().x(), width - 20)
            self.assertEqual(note.resize_handle.cursor().shape(), Qt.CursorShape.SizeFDiagCursor)
            with fitz.open(path) as check:
                page = check[0]
                annotations = list(page.annots())
                self.assertEqual(len(annotations), 1)
                self.assertAlmostEqual(annotations[0].rect.width, width / viewer.zoom)
                self.assertAlmostEqual(annotations[0].rect.height, (height - 24) / viewer.zoom)
                self.assertEqual(annotations[0].info["content"], "Nota")

        note.set_size(1, 1)
        self.assertEqual(note.rect().width(), note.MIN_WIDTH)
        self.assertGreaterEqual(note.rect().height(), note.MIN_HEIGHT)
        note.text_item.setPlainText("Testo lungo che va a capo. " * 12)
        self.assertEqual(note.rect().width(), note.MIN_WIDTH)
        self.assertGreaterEqual(note.rect().height(), note.text_item.document().size().height() + 34)
        viewer.viewport().repaint()

    def test_29_resized_postit_dimensions_survive_zoom_pages_and_reopening(self):
        path = os.path.join(self.tmp.name, "resize-persistent.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima pagina")
            doc.insert_page(-1, text="seconda pagina")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        note = PostItItem("Dimensioni salvate", 100, 100)
        viewer.scene_obj.addItem(note)
        note.set_size(360, 220)
        self.window.viewer.editor.save_file()
        with fitz.open(path) as check:
            page = check[0]
            expected = fitz.Rect(list(page.annots())[0].rect)

        for zoom in (0.5, 5.0, 2.0):
            viewer.zoom_by(zoom - viewer.zoom)
            notes = [item for item in viewer.scene_obj.items() if isinstance(item, PostItItem)]
            self.assertEqual(len(notes), 1)
            reloaded = notes[0]
            self.assertAlmostEqual(reloaded.rect().width() * reloaded.scale() / viewer.zoom, expected.width)
            self.assertAlmostEqual((reloaded.rect().height() - 24) * reloaded.scale() / viewer.zoom, expected.height)
            self.assertAlmostEqual(reloaded.x() / viewer.zoom, expected.x0)
            self.assertAlmostEqual((reloaded.y() + 24 * reloaded.scale()) / viewer.zoom, expected.y0)
            self.window.viewer.editor.save_file()
            with fitz.open(path) as check:
                page = check[0]
                self.assertEqual(list(page.annots())[0].rect, expected)

        self.window.next_page()
        self.window.prev_page()
        self.window.viewer.editor.save_file()
        viewer.pdf_doc.close()
        viewer.load_pdf(path)
        notes = [item for item in viewer.scene_obj.items() if isinstance(item, PostItItem)]
        self.assertEqual(len(notes), 1)
        self.assertAlmostEqual(notes[0].rect().width(), 360)
        self.assertAlmostEqual(notes[0].rect().height(), 220)
        self.assertEqual(notes[0].text_item.toPlainText(), "Dimensioni salvate")

    def test_30_undo_highlight_and_eraser_persists_to_pdf(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "undo-highlight.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        _app.processEvents()
        viewer.ensureVisible(QRectF(80, 80, 200, 100))
        word = viewer.words[0]
        point = viewer.mapFromScene(QPointF((word[0] + word[2]) * viewer.zoom / 2,
            (word[1] + word[3]) * viewer.zoom / 2))
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(len(self.window.viewer.editor.undo_stack), 1)
        page = viewer.pdf_doc[0]
        self.assertEqual(len(list(page.annots())), 1)
        self.window.tools.radio_erase.click()
        QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(len(self.window.viewer.editor.undo_stack), 2)
        self.assertEqual(list(viewer.pdf_doc[0].annots()), [])
        QTest.keySequence(viewer, QKeySequence(QKeySequence.StandardKey.Undo))
        self.assertEqual(len(list(viewer.pdf_doc[0].annots())), 1)
        QTest.keySequence(viewer, QKeySequence(QKeySequence.StandardKey.Undo))
        self.assertEqual(list(viewer.pdf_doc[0].annots()), [])
        with fitz.open(path) as doc:
            self.assertEqual(list(doc[0].annots()), [])
        self.assertEqual(self.window.viewer.editor.undo_stack, [])

    def test_31_undo_postit_resize_color_delete_and_creation(self):
        path = os.path.join(self.tmp.name, "undo-note.pdf")
        self._make_pdf(path)
        self.window.viewer.load_pdf(path)
        viewer = self.window.viewer
        note = PostItItem("Nota", 100, 100)
        viewer.scene_obj.addItem(note)
        self.window.viewer.editor.save_file()
        note.set_size(360, 200)
        self.window.viewer.editor.save_file()
        note.palette.show()
        note.handle_click(note.color_btns[1].sceneBoundingRect().center())
        note.handle_click(note.close_btn.sceneBoundingRect().center())
        self.assertEqual(len(self.window.viewer.editor.undo_stack), 4)
        for width, color in [(360, "#b5f5b5"), (360, "#fceea7"), (180, "#fceea7")]:
            self.window.viewer.editor.undo_last_action()
            notes = [it for it in viewer.scene_obj.items() if isinstance(it, PostItItem)]
            self.assertEqual(len(notes), 1)
            self.assertAlmostEqual(notes[0].rect().width(), width)
            self.assertEqual(notes[0].bg_color, color)
            self.assertEqual(notes[0].text_item.toPlainText(), "Nota")
        self.window.viewer.editor.undo_last_action()
        self.assertFalse(any(isinstance(it, PostItItem) for it in viewer.scene_obj.items()))

    def test_32_undo_text_in_postit_does_not_delete_the_note(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "undo-text.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        note = PostItItem("", 100, 100)
        viewer.scene_obj.addItem(note)
        self.window.viewer.editor.save_file()
        note.text_item.setFocus()
        _app.processEvents()
        QTest.keyClicks(viewer.viewport(), "testo")
        self.window.viewer.editor.save_file()
        QTest.keySequence(viewer.viewport(), QKeySequence(QKeySequence.StandardKey.Undo))
        self.assertEqual(note.text_item.toPlainText(), "")
        self.assertIs(note.scene(), viewer.scene_obj)
        QTest.keySequence(viewer.viewport(), QKeySequence(QKeySequence.StandardKey.Undo))
        self.assertFalse(any(isinstance(it, PostItItem) for it in viewer.scene_obj.items()))

    def test_33_resume_restores_vault_pdf_page_and_zoom(self):
        path = os.path.join(self.tmp.name, "session.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima")
            doc.insert_page(-1, text="seconda")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.next_page()
        viewer.zoom_by(0.3)
        selector = VaultSelector()
        self.assertTrue(selector.resume_button.isEnabled())
        selector.resume_button.click()
        self.assertEqual(selector.selected_path, self.tmp.name)
        restored = MainWindow(selector.selected_path, selector.resume_session)
        try:
            self.assertEqual(restored.viewer.pdf_doc.name, path)
            self.assertEqual(restored.viewer.current_page_num, 1)
            self.assertAlmostEqual(restored.viewer.zoom, 2.3)
            self.assertEqual(restored.viewer.editor.undo_stack, [])
        finally:
            restored.close()
            restored.deleteLater()
            selector.deleteLater()

    def test_34_search_finds_nested_folders_and_pdfs_and_filters_recent_vaults(self):
        folder = os.path.join(self.tmp.name, "Libri", "Sistemi")
        os.makedirs(folder)
        path = os.path.join(folder, "Operating Systems.pdf")
        self._make_pdf(path)
        with open(os.path.join(folder, "ignore.txt"), "w") as f:
            f.write("Systems")
        self.window.vault_browser.folder_search.setText("systems")
        self.window.vault_browser.start_folder_search()
        self.window.vault_browser.search_future.result(timeout=5)
        self.window.vault_browser.poll_folder_search()
        self.assertEqual(self.window.vault_browser.search_results.count(), 1)
        result = self.window.vault_browser.search_results.item(0)
        self.assertEqual(result.data(Qt.ItemDataRole.UserRole), path)
        self.window.vault_browser.open_search_result(result)
        self.assertEqual(self.window.viewer.pdf_doc.name, path)
        self.window.vault_browser.folder_search.setText("sistemi")
        self.window.vault_browser.start_folder_search()
        self.window.vault_browser.search_future.result(timeout=5)
        self.window.vault_browser.poll_folder_search()
        self.assertEqual(self.window.vault_browser.search_results.item(0).data(Qt.ItemDataRole.UserRole), folder)
        self.window.vault_browser.open_search_result(self.window.vault_browser.search_results.item(0))
        self.assertEqual(self.window.vault_browser.folder_search.text(), "")
        self.assertEqual(self.window.vault_browser.sidebar.currentIndex(), self.window.vault_browser.file_model.index(folder))
        selector = VaultSelector()
        selector.save_recent_vault(folder)
        selector.recent_list.clear()
        selector.load_recent_vaults()
        selector.vault_search.setText("sistemi")
        self.assertFalse(selector.recent_list.item(0).isHidden())
        selector.vault_search.setText("inesistente")
        self.assertTrue(selector.recent_list.item(0).isHidden())
        selector.deleteLater()

    def test_35_navigation_and_save_do_not_add_undo_actions(self):
        path = os.path.join(self.tmp.name, "undo-pages.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima pagina")
            doc.insert_page(-1, text="seconda pagina")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        note = PostItItem("Nota nella prima pagina", 100, 100)
        viewer.scene_obj.addItem(note)
        self.window.viewer.editor.save_file()
        self.window.next_page()
        self.window.viewer.editor.save_file()
        viewer.zoom_by(0.2)
        self.assertEqual(len(self.window.viewer.editor.undo_stack), 1)
        self.window.viewer.editor.undo_last_action()
        self.assertEqual(viewer.current_page_num, 0)
        self.assertFalse(any(isinstance(it, PostItItem) for it in viewer.scene_obj.items()))
        with fitz.open(path) as doc:
            self.assertEqual(len(doc), 2)
            self.assertIn("prima pagina", doc[0].get_text())
            self.assertIn("seconda pagina", doc[1].get_text())

    def test_36_resume_uses_recent_vault_before_first_saved_session(self):
        os.remove(settings.SESSION_FILE)
        with open(settings.HISTORY_FILE, "w") as f:
            json.dump([self.tmp.name], f)
        selector = VaultSelector()
        self.assertTrue(selector.resume_button.isEnabled())
        selector.resume_button.click()
        self.assertEqual(selector.selected_path, self.tmp.name)
        selector.deleteLater()

    def test_37_saving_second_page_keeps_unchanged_notes_on_first_page(self):
        path = os.path.join(self.tmp.name, "notes-on-pages.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima pagina")
            doc.insert_page(-1, text="seconda pagina")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        viewer.scene_obj.addItem(PostItItem("Prima nota", 100, 100))
        self.window.viewer.editor.save_file()
        viewer.render_page()
        self.window.next_page()
        viewer.scene_obj.addItem(PostItItem("Seconda nota", 100, 100))
        self.window.viewer.editor.save_file()
        with fitz.open(path) as doc:
            for index, text in [(0, "Prima nota"), (1, "Seconda nota")]:
                page = doc[index]
                self.assertEqual([annot.info["content"] for annot in page.annots()], [text])
        self.window.viewer.editor.undo_last_action()
        with fitz.open(path) as doc:
            page = doc[0]
            self.assertEqual([annot.info["content"] for annot in page.annots()], ["Prima nota"])
            self.assertEqual(list(doc[1].annots()), [])

    def _fake_antigravity(self):
        executable = os.path.join(self.tmp.name, "agy")
        log = os.path.join(self.tmp.name, "requests.jsonl")
        script = """import json, sys, time, os
with open(LOG + '.starts', 'a') as f:
    f.write(json.dumps({'arguments': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
print(json.dumps({'event': 'init', 'conversation_id': 'test-conversation'}), flush=True)
counter = 0
for line in sys.stdin:
    message = json.loads(line)
    with open(LOG, 'a') as f:
        f.write(json.dumps(message) + '\\n')
    counter += 1
    content = message['message']['content']
    if 'FORZA_ERRORE' in content:
        print(json.dumps({'event': 'result', 'result': {'status': 'ERROR', 'error': 'authentication required'}}), flush=True)
        continue
    if 'RALLENTA' in content:
        time.sleep(30)
    answer = 'Risposta ' + str(counter) + ': caffè ☕'
    delta = json.dumps({'event': 'step_update', 'step_update': {'step_type': 'agent_response', 'text_delta': answer}}, ensure_ascii=False).encode() + b'\\n'
    split = delta.index('è'.encode()) + 1
    sys.stdout.buffer.write(delta[:split]); sys.stdout.buffer.flush()
    time.sleep(0.02)
    sys.stdout.buffer.write(delta[split:]); sys.stdout.buffer.flush()
    print(json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': answer}}), flush=True)
"""
        with open(executable, "w") as f:
            f.write("#!" + sys.executable + "\nLOG = " + repr(log) + "\n" + script)
        os.chmod(executable, 0o755)
        return executable, log

    def _wait_for_ai_reply(self):
        import time
        from PyQt6.QtTest import QTest
        deadline = time.monotonic() + 5
        while self.window.ai_panel.busy and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(self.window.ai_panel.busy, self.window.ai_panel.status.text())

    def test_38_antigravity_streams_unicode_and_keeps_one_process_for_the_chat(self):
        executable, log = self._fake_antigravity()
        panel = self.window.ai_panel
        panel.context = lambda: ("Pagina 2 · libro.pdf", "Testo di prova")
        with patch("ai_panel.shutil.which", return_value=executable):
            panel.prompt.setPlainText("Spiegami il testo")
            panel.send_button.click()
            process = panel.process
            self.assertTrue(panel.busy)
            self._wait_for_ai_reply()
            self.assertEqual(panel.messages[-1], ("Antigravity", "Risposta 1: caffè ☕"))
            panel.include_context.setChecked(False)
            panel.prompt.setPlainText("Ora fai un esempio")
            panel.send()
            self._wait_for_ai_reply()
            self.assertIs(panel.process, process)
            self.assertEqual(panel.messages[-1], ("Antigravity", "Risposta 2: caffè ☕"))
        with open(log) as f:
            requests = [json.loads(line)["message"]["content"] for line in f]
        self.assertIn("Testo di prova", requests[0])
        self.assertNotIn("Testo di prova", requests[1])
        self.assertEqual(panel.status.text(), "Pronto")
        self.assertEqual(panel.conversation_id, "test-conversation")
        self.assertFalse(panel.stop_button.isEnabled())
        panel.new_button.click()
        self.assertEqual(panel.messages, [])
        self.assertIsNone(panel.conversation_id)

    def test_39_antigravity_error_retains_question_and_stop_closes_process(self):
        from PyQt6.QtCore import QProcess
        from PyQt6.QtTest import QTest
        executable, _ = self._fake_antigravity()
        panel = self.window.ai_panel
        with patch("ai_panel.shutil.which", return_value=executable):
            panel.prompt.setPlainText("FORZA_ERRORE")
            panel.send()
            self._wait_for_ai_reply()
            self.assertIn("Accedi ad Antigravity", panel.status.text())
            self.assertEqual(panel.prompt.toPlainText(), "FORZA_ERRORE")
            panel.prompt.setPlainText("RALLENTA")
            panel.send()
            process = panel.process
            QTest.qWait(50)
            panel.stop_button.click()
            self.assertFalse(panel.busy)
            self.assertEqual(panel.status.text(), "Risposta interrotta.")
            self.assertEqual(panel.prompt.toPlainText(), "RALLENTA")
            self.assertTrue(process.waitForFinished(1500))
            self.assertEqual(process.state(), QProcess.ProcessState.NotRunning)

    def test_40_antigravity_uses_pdf_selection_or_page_and_can_be_hidden(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "chat-context.pdf")
        self._make_pdf(path)
        self.window.viewer.load_pdf(path)
        label, text = self.window.ai_context()
        self.assertIn("Pagina 1", label)
        self.assertIn("test page", text)
        self.window.viewer.text_selection = (0, 0)
        label, text = self.window.ai_context()
        self.assertIn("Selezione", label)
        self.assertEqual(text, "test")
        self.window.show()
        _app.setActiveWindow(self.window)
        panel = self.window.ai_panel
        panel.prompt.setFocus()
        _app.processEvents()
        QTest.keyClicks(panel.prompt, "adeqp123")
        self.assertEqual(panel.prompt.toPlainText(), "adeqp123")
        self.assertEqual(self.window.viewer.mode, "highlight")
        self.assertEqual(self.window.viewer.current_page_num, 0)
        self.window.ai_toggle.click()
        self.assertTrue(panel.isHidden())
        self.window.ai_toggle.click()
        self.assertFalse(panel.isHidden())

    def test_41_missing_antigravity_keeps_question_editable(self):
        panel = self.window.ai_panel
        panel.prompt.setPlainText("Domanda")
        with patch("ai_panel.shutil.which", return_value=None), patch("ai_panel.os.path.isfile", return_value=False):
            panel.send()
        self.assertFalse(panel.busy)
        self.assertEqual(panel.prompt.toPlainText(), "Domanda")
        self.assertIn("non trovato", panel.status.text())

    def test_42_bookmarks_persist_and_return_to_page_and_position(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "bookmarks.pdf")
        with fitz.open() as doc:
            doc.insert_page(-1, text="prima pagina")
            doc.insert_page(-1, text="seconda pagina")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.processEvents()
        viewer.centerOn(500, 800)
        viewer.bookmark_button.click()
        self.assertTrue(viewer.bookmark_button.isChecked())
        self.assertTrue(self.window.reading_notes.is_bookmarked(0))
        self.assertEqual(self.window.sidebar_tabs.currentWidget(), self.window.reading_notes)
        saved = self.window.reading_notes.current_bookmarks()[0]
        with open(settings.BOOKMARKS_FILE) as f:
            self.assertEqual(json.load(f)[os.path.abspath(path)][0], saved)
        self.window.next_page()
        self.assertFalse(viewer.bookmark_button.isChecked())
        bookmarks = self.window.reading_notes.bookmark_list
        item = bookmarks.item(0)
        QTest.mouseClick(bookmarks.viewport(), Qt.MouseButton.LeftButton, pos=bookmarks.visualItemRect(item).center())
        self.assertEqual(viewer.current_page_num, 0)
        self.assertTrue(viewer.bookmark_button.isChecked())
        center = viewer.mapToScene(viewer.viewport().rect().center())
        self.assertAlmostEqual(center.y() / viewer.zoom, saved["point"][1], delta=1)
        restored = MainWindow(self.tmp.name)
        try:
            restored.viewer.load_pdf(path)
            self.assertTrue(restored.reading_notes.is_bookmarked(0))
            self.assertTrue(restored.viewer.bookmark_button.isChecked())
            restored.viewer.bookmark_button.click()
            self.assertFalse(restored.reading_notes.is_bookmarked(0))
            with open(settings.BOOKMARKS_FILE) as f:
                self.assertEqual(json.load(f)[os.path.abspath(path)], [])
        finally:
            restored.close()
            restored.deleteLater()

    def test_43_highlight_cards_show_exact_text_and_jump_to_the_highlight(self):
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QLabel
        path = os.path.join(self.tmp.name, "highlight-cards.pdf")
        with fitz.open() as doc:
            for text in ("Primo testo evidenziato qui", "Pagina senza appunti", "Ultimo testo evidenziato qui"):
                page = doc.new_page()
                page.insert_text((72, 550), text)
                if len(doc) != 2:
                    words = page.get_text("words")[:3]
                    annotation = page.add_highlight_annot([fitz.Rect(word[:4]).quad for word in words])
                    annotation.set_colors(stroke=(0.71, 0.96, 0.71))
                    annotation.update()
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        self.window.sidebar_tabs.setCurrentWidget(self.window.reading_notes)
        _app.processEvents()
        self.window.reading_notes.scan_batch()
        highlights = self.window.reading_notes.highlight_list
        self.assertEqual(highlights.count(), 2)
        first = highlights.item(0).data(Qt.ItemDataRole.UserRole)
        last_item = highlights.item(1)
        last = last_item.data(Qt.ItemDataRole.UserRole)
        self.assertEqual(first["text"], "Primo testo evidenziato")
        self.assertEqual(last["text"], "Ultimo testo evidenziato")
        self.assertEqual(last["page"], 2)
        card = highlights.itemWidget(last_item)
        label = card.findChildren(QLabel)[-1]
        point = label.mapTo(card, label.rect().center())
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(viewer.current_page_num, 2)
        center = viewer.mapToScene(viewer.viewport().rect().center())
        self.assertAlmostEqual(center.y() / viewer.zoom, last["point"][1], delta=1)

    def test_44_highlight_cards_refresh_after_changes_undo_and_switching_pdf(self):
        path = os.path.join(self.tmp.name, "changing-highlights.pdf")
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        page = viewer.pdf_doc[0]
        annotation = page.add_highlight_annot(fitz.Rect(page.get_text("words")[0][:4]).quad)
        annotation.update()
        self.window.viewer.editor.save_file()
        self.assertEqual(self.window.reading_notes.highlight_label.text(), "Evidenziazioni (1)")
        self.window.viewer.editor.undo_last_action()
        self.assertEqual(self.window.reading_notes.highlight_label.text(), "Evidenziazioni (0)")
        other = os.path.join(self.tmp.name, "other.pdf")
        self._make_pdf(other)
        viewer.load_pdf(other)
        _app.processEvents()
        self.assertEqual(self.window.reading_notes.highlight_label.text(), "Evidenziazioni (0)")
        self.assertFalse(viewer.bookmark_button.isChecked())
    def test_45_highlight_click_survives_background_scan_and_sidebar_resize(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "background-notes.pdf")
        with fitz.open() as doc:
            for number in range(30):
                page = doc.new_page()
                page.insert_text((72, 600), f"Nota {number}")
                annotation = page.add_highlight_annot(page.search_for("Nota", quads=True))
                annotation.update()
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        notes = self.window.reading_notes
        notes.timer.stop()
        self.window.sidebar_tabs.setCurrentWidget(notes)
        _app.processEvents()
        notes.scan_batch()
        item = notes.highlight_list.item(0)
        card = notes.highlight_list.itemWidget(item)
        position = card.rect().center()
        viewer.centerOn(500, 150)
        QTest.mousePress(card, Qt.MouseButton.LeftButton, pos=position)
        notes.scan_batch()
        notes.layout_cards()
        self.assertIs(notes.highlight_list.itemWidget(item), card)
        QTest.mouseRelease(card, Qt.MouseButton.LeftButton, pos=position)
        _app.processEvents()
        record = item.data(Qt.ItemDataRole.UserRole)
        center = viewer.mapToScene(viewer.viewport().rect().center())
        self.assertAlmostEqual(center.y() / viewer.zoom, record["point"][1], delta=1)

    def test_46_rotated_highlight_target_matches_displayed_page(self):
        from reading_notes import extract_highlight
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), fitz.open() as doc:
                page = doc.new_page(width=400, height=600)
                page.insert_text((70, 450), "Testo ruotato")
                quad = page.search_for("Testo ruotato", quads=True)[0]
                annotation = page.add_highlight_annot(quad)
                annotation.update()
                page.set_rotation(rotation)
                text, point = extract_highlight(page, annotation)
                expected = quad.rect.tl + (quad.rect.br - quad.rect.tl) / 2
                expected *= page.rotation_matrix
                self.assertEqual(text, "Testo ruotato")
                self.assertAlmostEqual(point[0], expected.x, places=3)
                self.assertAlmostEqual(point[1], expected.y, places=3)

    def test_47_chat_enter_sends_shift_enter_keeps_newline(self):
        from PyQt6.QtTest import QTest
        executable, log = self._fake_antigravity()
        panel = self.window.ai_panel
        self.window.show()
        _app.setActiveWindow(self.window)
        panel.prompt.setFocus()
        with patch("ai_panel.shutil.which", return_value=executable):
            QTest.keyClicks(panel.prompt, "Prima riga")
            QTest.keyClick(panel.prompt, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
            QTest.keyClicks(panel.prompt, "Seconda riga")
            self.assertEqual(panel.prompt.toPlainText(), "Prima riga\nSeconda riga")
            self.assertFalse(panel.busy)
            QTest.keyClick(panel.prompt, Qt.Key.Key_Return)
            self.assertTrue(panel.busy)
            QTest.keyClick(panel.prompt, Qt.Key.Key_Return)
            self._wait_for_ai_reply()
        with open(log) as f:
            requests = [json.loads(line) for line in f]
        self.assertEqual(len(requests), 1)
        self.assertIn("Prima riga\nSeconda riga", requests[0]["message"]["content"])

    def _chat_dom(self, expression, predicate=lambda value: value, timeout=15000, transcript=None):
        from PyQt6.QtTest import QTest
        from time import monotonic
        transcript = transcript or self.window.ai_panel.transcript
        deadline = monotonic() + timeout / 1000
        last = None
        while monotonic() < deadline:
            result = []
            if transcript.ready:
                transcript.browser.page().runJavaScript(expression, result.append)
                while not result and monotonic() < deadline:
                    QTest.qWait(10)
                if result:
                    last = result[0]
                    if predicate(last):
                        return last
            QTest.qWait(40)
        self.fail(f"Chat non pronta: {last!r}")

    def test_48_chat_renders_markdown_diagrams_math_and_copy(self):
        from PyQt6.QtWidgets import QDialog
        from PyQt6.QtTest import QTest
        from chat_renderer import ChatTranscript
        panel = self.window.ai_panel
        panel.messages = [("Tu", "<b>Domanda</b>"), ("Antigravity", '''## Flusso

**Spiegazione** con $x^2$.

| Campo | Valore |
| --- | --- |
| Stato | Attivo |

```python
print("ciao")
```

```mermaid
flowchart TD
A[Input] --> B[Output]
```

<script>window.untrusted = true;</script><img src="https://test.invalid/image.png">
''')]
        self.window.show()
        panel.render_messages()
        stats = self._chat_dom("({heading:!!document.querySelector('h2'),table:!!document.querySelector('table'),code:!!document.querySelector('.hljs-built_in'),math:!!document.querySelector('.katex'),svg:!!document.querySelector('.diagram-canvas svg'),sourceHidden:!!document.querySelector('.diagram-block pre[hidden]'),unsafe:!!window.untrusted || !!document.querySelector('.body img'),user:document.querySelector('.user .body').textContent})", lambda s: s and s.get("sourceHidden"))
        for field in ("heading", "table", "code", "math", "svg"):
            self.assertTrue(stats[field], field)
        self.assertFalse(stats["unsafe"])
        self.assertEqual(stats["user"], "<b>Domanda</b>")
        self._chat_dom("document.querySelector('.code-block .block-header button').click(); true")
        for _ in range(100):
            if _app.clipboard().text().strip() == 'print("ciao")':
                break
            QTest.qWait(10)
        self.assertEqual(_app.clipboard().text().strip(), 'print("ciao")')
        self._chat_dom("Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Espandi').click(); true")
        for _ in range(100):
            dialogs = self.window.findChildren(QDialog)
            if dialogs:
                break
            QTest.qWait(10)
        self.assertTrue(dialogs)
        dialog = dialogs[-1]
        diagram = dialog.findChild(ChatTranscript)
        try:
            width = self._chat_dom("document.querySelector('.diagram-mode svg')?.style.width", transcript=diagram)
            self._chat_dom("Array.from(document.querySelectorAll('button')).find(b => b.textContent === '+').click(); true", transcript=diagram)
            larger = self._chat_dom("document.querySelector('.diagram-mode svg').style.width", lambda v: v != width, transcript=diagram)
            self.assertGreater(float(larger[:-2]), float(width[:-2]))
        finally:
            dialog.close()

    def test_49_close_and_undo_postit_crossing_page_edge_with_chat_open(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, "edge-note.pdf")
        with fitz.open() as doc:
            page = doc.new_page(width=432, height=648)
            page.insert_text((70, 330), "Pagina con appunto")
            note = page.add_freetext_annot(fitz.Rect(-46.875, 392.625, 43.125, 457.625),
                "Testo del post-it fuori dal bordo della pagina", fontsize=12, fill_color=(0.98, 0.93, 0.65))
            note.update()
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path, zoom=1.6)
        self.window.show()
        self.window.ai_panel.messages = [("Antigravity", "Chat aperta durante le modifiche")]
        self.window.ai_panel.render_messages()
        _app.processEvents()
        for cycle in range(60):
            notes = [n for n in viewer.scene_obj.items() if isinstance(n, PostItItem)]
            self.assertEqual(len(notes), 1, cycle)
            note = notes[0]
            viewer.centerOn(0, 690)
            viewer.ensureVisible(note)
            _app.processEvents()
            note.text_item.setFocus()
            QTest.qWait(2)
            point = viewer.mapFromScene(note.close_btn.sceneBoundingRect().center())
            QTest.mouseClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
            _app.processEvents()
            viewer.viewport().repaint()
            self.assertFalse(any(isinstance(n, PostItItem) for n in viewer.scene_obj.items()))
            self.window.viewer.editor.undo_last_action()
            _app.processEvents()
            viewer.viewport().repaint()

    def test_50_editable_page_counter_jumps_saves_and_tracks_navigation(self):
        from PyQt6.QtTest import QTest
        self.assertFalse(self.window.page_input.isEnabled())
        path = os.path.join(self.tmp.name, "page-counter.pdf")
        with fitz.open() as doc:
            for _ in range(5):
                doc.insert_page(-1, text="Pagina del PDF")
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        self.window.show()
        _app.setActiveWindow(self.window)
        _app.processEvents()
        control = self.window.page_input
        self.assertTrue(control.isEnabled())
        self.assertEqual(control.value(), 1)
        self.assertEqual(control.maximum(), 5)
        self.assertEqual(self.window.page_count.text(), "/ 5")
        viewer.scene_obj.addItem(PostItItem("Nota prima del salto", 100, 100))
        control.setFocus()
        control.lineEdit().selectAll()
        QTest.keyClicks(control, "4")
        self.assertEqual(viewer.current_page_num, 0)
        QTest.keyClick(control, Qt.Key.Key_Return)
        self.assertEqual(viewer.current_page_num, 3)
        self.assertEqual(control.value(), 4)
        self.assertEqual(self.window.tools.current_color, "Giallo")
        with fitz.open(path) as doc:
            page = doc[0]
            self.assertEqual(next(page.annots()).info["content"], "Nota prima del salto")
        self.window.next_page()
        self.assertEqual(control.value(), 5)
        self.window.jump_to_note(1, (100, 500))
        self.assertEqual(control.value(), 2)
        control.setValue(999)
        self.assertEqual(viewer.current_page_num, 4)
        other = os.path.join(self.tmp.name, "short.pdf")
        self._make_pdf(other)
        viewer.load_pdf(other)
        self.assertEqual(control.value(), 1)
        self.assertEqual(control.maximum(), 1)
        self.assertEqual(self.window.page_count.text(), "/ 1")

    def test_51_chat_reopens_same_conversation_and_history_keeps_previous_chats(self):
        executable, log = self._fake_antigravity()
        panel = self.window.ai_panel
        with patch("ai_panel.shutil.which", return_value=executable):
            panel.prompt.setPlainText("Prima conversazione")
            panel.send()
            self._wait_for_ai_reply()
        previous = list(panel.messages)
        chat_id = panel.session.id
        workspace = str(panel.history.workspace)
        panel.include_context.setChecked(False)
        panel.prompt.setPlainText("Bozza da riprendere")
        old = self.window
        old.close()
        old.deleteLater()
        self.window = MainWindow(self.tmp.name)
        panel = self.window.ai_panel
        self.assertEqual(panel.messages, previous)
        self.assertEqual(panel.conversation_id, "test-conversation")
        self.assertEqual(panel.prompt.toPlainText(), "Bozza da riprendere")
        self.assertFalse(panel.include_context.isChecked())
        with patch("ai_panel.shutil.which", return_value=executable):
            panel.send()
            self._wait_for_ai_reply()
        with open(log + '.starts') as f:
            starts = [json.loads(line) for line in f]
        self.assertEqual(starts[0]["cwd"], os.path.realpath(workspace))
        self.assertEqual(starts[1]["cwd"], os.path.realpath(workspace))
        self.assertNotIn("--conversation", starts[0]["arguments"])
        args = starts[1]["arguments"]
        self.assertEqual(args[args.index("--conversation") + 1], "test-conversation")
        panel.new_button.click()
        self.assertNotEqual(panel.session.id, chat_id)
        self.assertEqual(panel.messages, [])
        self.assertIsNone(panel.conversation_id)
        panel.populate_history()
        self.assertEqual(len(panel.history_menu.actions()), 1)
        panel.history_menu.actions()[0].trigger()
        self.assertEqual(panel.session.id, chat_id)
        self.assertEqual(panel.messages[:2], previous)
        self.assertEqual(panel.conversation_id, "test-conversation")

    def test_52_chat_history_ignores_invalid_files_and_separates_vaults(self):
        from chat_history import ChatHistory, ChatSession
        root = os.path.join(self.tmp.name, 'history')
        history = ChatHistory(root, self.tmp.name)
        session = ChatSession(messages=[("Tu", "Domanda"), ("Antigravity", "Risposta")])
        history.save(session)
        other = ChatHistory(root, os.path.join(self.tmp.name, 'other-vault'))
        self.assertIsNone(other.latest())
        self.assertEqual(other.entries(), [])
        (history.directory / (session.id + '.json')).write_text('{broken')
        (history.directory / 'invalid.json').write_text('{}')
        self.assertIsNone(history.latest())
        self.assertEqual(history.entries(), [])
        (history.directory / 'active').write_text('../outside')
        self.assertIsNone(history.latest())

    def test_53_postit_name_persists_survives_zoom_and_is_undoable(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, 'named-notes.pdf')
        self._make_pdf(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        note = PostItItem("Corpo della nota", 100, 300)
        viewer.scene_obj.addItem(note)
        self.window.viewer.editor.save_file()
        self.window.show()
        viewer.ensureVisible(note)
        _app.processEvents()
        point = viewer.mapFromScene(note.title_item.sceneBoundingRect().center())
        with patch('postits.QInputDialog.getText', return_value=('Memoria virtuale', True)):
            QTest.mouseDClick(viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(note.title, 'Memoria virtuale')
        with fitz.open(path) as doc:
            page = doc[0]
            self.assertEqual(next(page.annots()).info['subject'], 'Memoria virtuale')
        self.assertIn('Memoria virtuale', self.window.reading_notes.postit_list.item(0).text())
        viewer.zoom_by(.1)
        reloaded = next(n for n in viewer.scene_obj.items() if isinstance(n, PostItItem))
        self.assertEqual(reloaded.title, 'Memoria virtuale')
        viewer.editor.undo_last_action()
        restored = next(n for n in viewer.scene_obj.items() if isinstance(n, PostItItem))
        self.assertEqual(restored.title, 'Post-it')

    def test_54_postit_list_includes_old_notes_and_jumps_across_pages(self):
        from PyQt6.QtTest import QTest
        path = os.path.join(self.tmp.name, 'all-postits.pdf')
        with fitz.open() as doc:
            for name in ('', 'Processi'):
                page = doc.new_page()
                note = page.add_freetext_annot(fitz.Rect(100, 500, 190, 580), 'Testo appunto')
                note.set_info(subject=name)
                note.update()
            doc.save(path)
        viewer = self.window.viewer
        viewer.load_pdf(path)
        notes = self.window.reading_notes
        notes.scan_batch()
        self.assertEqual(notes.postit_list.count(), 2)
        self.assertIn('Post-it', notes.postit_list.item(0).text())
        self.assertIn('Processi', notes.postit_list.item(1).text())
        self.window.show()
        self.window.sidebar_tabs.setCurrentWidget(notes)
        _app.processEvents()
        item = notes.postit_list.item(1)
        QTest.mouseClick(notes.postit_list.viewport(), Qt.MouseButton.LeftButton,
            pos=notes.postit_list.visualItemRect(item).center())
        self.assertEqual(viewer.current_page_num, 1)
        self.assertEqual(self.window.page_input.value(), 2)
        self.assertEqual(notes.postit_label.text(), 'Post-it (2)')
        note = next(n for n in viewer.scene_obj.items() if isinstance(n, PostItItem))
        note.handle_click(note.close_btn.sceneBoundingRect().center())
        self.assertEqual(notes.postit_label.text(), 'Post-it (1)')
        viewer.editor.undo_last_action()
        notes.scan_batch()
        self.assertEqual(notes.postit_label.text(), 'Post-it (2)')

    def test_55_mouse_toggles_tools_off_and_preserves_exclusive_selection(self):
        from PyQt6.QtTest import QTest
        self.window.show()
        _app.setActiveWindow(self.window)
        _app.processEvents()
        tools = self.window.tools
        for button, mode in ((tools.radio_high, 'highlight'), (tools.radio_post, 'postit'),
                (tools.radio_erase, 'eraser')):
            button.setChecked(True)
            self.assertEqual(self.window.viewer.mode, mode)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.assertEqual(self.window.viewer.mode, 'pointer')
            self.assertIsNone(tools.btn_group.checkedButton())
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.assertEqual(self.window.viewer.mode, mode)
            self.assertEqual(sum(b.isChecked() for b in tools.btn_group.buttons()), 1)
        QTest.mouseClick(tools.radio_high, Qt.MouseButton.LeftButton)
        self.assertTrue(tools.radio_high.isChecked())
        self.assertFalse(tools.radio_erase.isChecked())
        self.window.viewer.setFocus()
        QTest.qWait(50)
        _app.setActiveWindow(self.window)
        QTest.keyClick(self.window.viewer, Qt.Key.Key_E)
        self.assertEqual(self.window.viewer.mode, 'pointer')
        QTest.mouseClick(tools.radio_high, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.viewer.mode, 'highlight')

    def test_56_file_permissions_show_actual_target_and_require_explicit_choice(self):
        from PyQt6.QtWidgets import QMessageBox
        gate = self.window.ai_panel.file_permissions
        tool = {'name': 'write_to_file', 'args': {'TargetFile': 'appunto.txt', 'CodeContent': 'Testo da scrivere'}}
        observed = []
        def answer(dialog):
            observed.append((dialog.text(), dialog.detailedText()))
        with patch.object(QMessageBox, 'exec', answer), patch.object(QMessageBox, 'clickedButton', return_value=None):
            self.assertEqual(gate.authorize(tool)['decision'], 'deny')
        self.assertIn(str((gate.workspace / 'appunto.txt').resolve()), observed[0][0])
        self.assertEqual(observed[0][1], 'Testo da scrivere')
        def allow_button(dialog):
            return next(button for button in dialog.buttons() if button.text() == 'Consenti')
        with patch.object(QMessageBox, 'exec', answer), patch.object(QMessageBox, 'clickedButton', allow_button):
            self.assertEqual(gate.authorize(tool)['decision'], 'auto_approve')
        protected = {'name': 'write_to_file', 'args': {'TargetFile': '.agents/hooks.json', 'CodeContent': '{}'}}
        with patch.object(QMessageBox, 'exec') as dialog:
            self.assertEqual(gate.authorize(protected)['decision'], 'deny')
            self.assertEqual(gate.authorize({'name': 'write_to_file', 'args': {}})['decision'], 'deny')
            dialog.assert_not_called()

    def test_57_cli_hook_waits_for_gui_and_denies_without_george(self):
        import subprocess
        from pathlib import Path
        from PyQt6.QtCore import QProcess
        from PyQt6.QtTest import QTest
        gate = self.window.ai_panel.file_permissions
        environment = gate.prepare()
        tool = {'name': 'write_to_file', 'args': {'TargetFile': 'note.txt', 'CodeContent': 'Testo'}}
        decisions = []
        def authorize(request):
            decisions.append(request)
            return {'decision': 'auto_approve', 'reason': 'Test'}
        process = QProcess()
        process.setProcessEnvironment(environment)
        process.start(sys.executable, [str(Path(__file__).with_name('permission_hook.py'))])
        self.assertTrue(process.waitForStarted(2000))
        with patch.object(gate, 'authorize', side_effect=authorize):
            process.write((json.dumps({'toolCall': tool}) + '\n').encode())
            process.closeWriteChannel()
            for _ in range(100):
                QTest.qWait(10)
                if process.state() == QProcess.ProcessState.NotRunning:
                    break
        self.assertEqual(decisions, [tool])
        self.assertEqual(json.loads(process.readAllStandardOutput().data())['decision'], 'auto_approve')
        hooks = json.loads((gate.workspace / '.agents/hooks.json').read_text())
        self.assertIn('write_to_file', hooks['george-file-approval']['PreToolUse'][0]['matcher'])
        standalone = subprocess.run([sys.executable, str(Path(__file__).with_name('permission_hook.py'))],
            input=json.dumps({'toolCall': tool}), capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(standalone.stdout)['decision'], 'deny')


    def _styled_clipboard(self):
        from PyQt6.QtCore import QMimeData
        mime = QMimeData()
        mime.setText('Testo incollato\nSeconda riga')
        mime.setHtml('<p style="color:#ffffff; background-color:#0000ff; font-size:38pt; font-weight:700">Testo incollato</p><p>Seconda riga</p>')
        _app.clipboard().setMimeData(mime)

    def test_58_keyboard_paste_discards_source_style_and_undo_restores_selection(self):
        from PyQt6.QtGui import QTextCursor, QColor
        from PyQt6.QtTest import QTest
        self._styled_clipboard()
        viewer = self.window.viewer
        note = PostItItem('Sostituiscimi', 80, 200)
        viewer.scene_obj.addItem(note)
        self.window.show()
        _app.setActiveWindow(self.window)
        viewer.setFocus()
        note.text_item.setFocus()
        cursor = note.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.text_item.setTextCursor(cursor)
        _app.processEvents()
        QTest.keySequence(viewer.viewport(), QKeySequence(QKeySequence.StandardKey.Paste))
        self.assertEqual(note.text_item.toPlainText(), 'Testo incollato\nSeconda riga')
        cursor = note.text_item.textCursor()
        cursor.setPosition(1)
        formatting = cursor.charFormat()
        self.assertEqual(formatting.foreground().color(), QColor('black'))
        self.assertEqual(formatting.font().pointSizeF(), 13)
        self.assertFalse(formatting.font().bold())
        self.assertEqual(formatting.background().style(), Qt.BrushStyle.NoBrush)
        QTest.keySequence(viewer.viewport(), QKeySequence(QKeySequence.StandardKey.Undo))
        self.assertEqual(note.text_item.toPlainText(), 'Sostituiscimi')

    def test_59_right_click_paste_menu_has_plain_default_and_optional_rich_paste(self):
        from PyQt6.QtGui import QTextCursor, QColor, QContextMenuEvent
        from PyQt6.QtWidgets import QMenu
        self._styled_clipboard()
        note = PostItItem('', 80, 200)
        self.window.viewer.scene_obj.addItem(note)
        self.window.show()
        _app.setActiveWindow(self.window)
        _app.processEvents()
        choices = []
        def plain_choice(menu, position):
            actions = {action.text(): action for action in menu.actions()}
            choices.extend(actions)
            actions['Incolla'].trigger()
        viewport = self.window.viewer.viewport()
        point = self.window.viewer.mapFromScene(note.text_item.mapToScene(QPointF(10, 10)))
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, viewport.mapToGlobal(point))
        with patch.object(QMenu, 'exec', plain_choice):
            _app.sendEvent(viewport, event)
        self.assertTrue(event.isAccepted())
        self.assertIn('Incolla con lo stesso stile', choices)
        cursor = note.text_item.textCursor()
        cursor.setPosition(1)
        self.assertEqual(cursor.charFormat().foreground().color(), QColor('black'))
        note.text_item.setPlainText('')
        menu = note.text_item.create_context_menu()
        actions = {action.text(): action for action in menu.actions()}
        actions['Incolla con lo stesso stile'].trigger()
        self.assertIn('Testo incollato', note.text_item.toPlainText())
        cursor = note.text_item.textCursor()
        cursor.setPosition(1)
        self.assertEqual(cursor.charFormat().foreground().color(), QColor('white'))
        self.assertEqual(cursor.charFormat().font().pointSizeF(), 38)
        self.assertTrue(cursor.charFormat().font().bold())
        menu.deleteLater()

    def test_60_paste_handles_html_only_and_plain_text_after_styled_text(self):
        from PyQt6.QtCore import QMimeData
        from PyQt6.QtGui import QTextCursor, QColor
        mime = QMimeData()
        mime.setHtml('<b style="color:white">Solo HTML</b>')
        _app.clipboard().setMimeData(mime)
        note = PostItItem('', 80, 200)
        note.text_item.paste()
        self.assertEqual(note.text_item.toPlainText(), 'Solo HTML')
        note.text_item.setHtml('<span style="color:white; font-size:38pt">Vecchio stile</span>')
        cursor = note.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.text_item.setTextCursor(cursor)
        _app.clipboard().setText('Leggibile')
        note.text_item.paste()
        cursor = note.text_item.textCursor()
        cursor.setPosition(1)
        self.assertEqual(note.text_item.toPlainText(), 'Leggibile')
        self.assertEqual(cursor.charFormat().foreground().color(), QColor('black'))
        self.assertEqual(cursor.charFormat().font().pointSizeF(), 13)
        _app.clipboard().setMimeData(QMimeData())
        menu = note.text_item.create_context_menu()
        for action in menu.actions():
            if action.text().startswith('Incolla'):
                self.assertFalse(action.isEnabled())
        menu.deleteLater()


if __name__ == '__main__':
    unittest.main(verbosity=2)
