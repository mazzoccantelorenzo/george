import json
import os
from typing import Any, TYPE_CHECKING, cast

import fitz
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QGraphicsTextItem

from postits import PostItItem

if TYPE_CHECKING:
    from pdf_viewer import PDFViewer


class DocumentEditor(QObject):
    saved = pyqtSignal()
    changed = pyqtSignal()
    error = pyqtSignal(str, str)

    def __init__(self, viewer: "PDFViewer") -> None:
        super().__init__(viewer)
        self.viewer = viewer
        self.undo_stack: list[tuple[bytes, int, str]] = []
        self.page_states: dict[int, str] = {}
        self.last_saved_pdf = b""

    def annotation_state(self) -> str:
        if not self.viewer.pdf_doc:
            return ""
        viewer = self.viewer
        page = cast(Any, viewer.pdf_doc)[viewer.current_page_num]
        records = []
        for annotation in page.annots():
            if annotation.type[0] != fitz.PDF_ANNOT_FREE_TEXT:
                records.append([annotation.type[0], list(annotation.rect), annotation.vertices,
                    annotation.colors, annotation.info, annotation.opacity, annotation.flags])
        for item in viewer.scene_obj.items():
            if isinstance(item, PostItItem):
                scale = item.scale() / viewer.zoom
                rect = [item.x() / viewer.zoom, (item.y() + 24 * item.scale()) / viewer.zoom,
                    item.rect().width() * scale, (item.rect().height() - 24) * scale]
                records.append(["postit", [round(value, 4) for value in rect],
                    item.text_item.toPlainText(), [round(value, 5) for value in item.pdf_color], item.title])
        return json.dumps(sorted(records, key=json.dumps), sort_keys=True)


    def undo_last_action(self) -> None:
        if self.viewer.is_editing_postit():
            item = cast(QGraphicsTextItem, self.viewer.scene_obj.focusItem())
            document = item.document()
            if document and document.isUndoAvailable():
                document.undo()
                self.save_file(record_undo=False)
                if self.undo_stack and self.undo_stack[-1][1:] == (self.viewer.current_page_num, self.annotation_state()):
                    self.undo_stack.pop()
                return
        self.save_file()
        if not self.undo_stack or not self.viewer.pdf_doc:
            return
        snapshot, page, _ = self.undo_stack[-1]
        path = self.viewer.pdf_doc.name
        try:
            with open(path + ".tmp.pdf", "wb") as f:
                f.write(snapshot)
            os.replace(path + ".tmp.pdf", path)
        except OSError as error:
            self.error.emit("Annulla modifica", f"Non è stato possibile annullare: {error}")
            return
        self.undo_stack.pop()
        self.viewer.pdf_doc.close()
        self.viewer.pdf_doc = fitz.open(path)
        self.viewer.current_page_num = page
        self.last_saved_pdf = snapshot
        self.page_states.clear()
        self.viewer.render_page()
        self.saved.emit()


    def save_file(self, record_undo: bool = True) -> None:
        if not self.viewer.pdf_doc: return
        state = self.annotation_state()
        changed = state != self.page_states.get(self.viewer.current_page_num)
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
                scale = item.scale()
                header_offset = 24 * scale / self.viewer.zoom
                x, y = item.x() / self.viewer.zoom, item.y() / self.viewer.zoom
                w = cast(Any, item).rect().width() * scale / self.viewer.zoom
                h = (cast(Any, item).rect().height() - 24) * scale / self.viewer.zoom
                rect = fitz.Rect(x, y + header_offset, x+w, y+header_offset+h)
                text = cast(Any, item).text_item.toPlainText()

                annot = page.add_freetext_annot(rect, text, fontsize=12, text_color=(0,0,0), fill_color=cast(Any, item).pdf_color)
                annot.set_info(subject=cast(PostItItem, item).title)
                annot.update()
                # Salvataggio sicuro tramite file temporaneo per evitare corruzione della memoria
        if not changed:
            self.saved.emit()
            return
        try:
            doc = self.viewer.pdf_doc
            path = doc.name
            temp_path = path + ".tmp.pdf"
            # Un full save elimina il rischio di corrompere il file originale o l'oggetto in memoria
            doc.save(temp_path, encryption=fitz.PDF_ENCRYPT_KEEP)
            import os
            # Su Mac/Linux possiamo sovrascrivere il file anche se è aperto. L'inode originale viene mantenuto vivo dal SO.
            os.replace(temp_path, path)
            if changed and record_undo and self.last_saved_pdf:
                self.undo_stack.append((self.last_saved_pdf, self.viewer.current_page_num,
                    self.page_states.get(self.viewer.current_page_num, "")))
                size = sum(len(frame[0]) for frame in self.undo_stack)
                while len(self.undo_stack) > 1 and (len(self.undo_stack) > 30 or size > 128 * 1024 * 1024):
                    size -= len(self.undo_stack.pop(0)[0])
            with open(path, "rb") as f:
                self.last_saved_pdf = f.read()
            self.page_states[self.viewer.current_page_num] = state
            self.saved.emit()
            self.changed.emit()
        except Exception as e:
            print("Auto-save fallito:", e)
