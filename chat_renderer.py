import json
import os
import sys
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget

if QCoreApplication.instance() is None:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

_interceptor: Optional[QObject] = None


def assets_path() -> str:
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "chat_assets")


class ChatBridge(QObject):
    def __init__(self, view: "ChatTranscript") -> None:
        super().__init__(view)
        self.view = view

    @pyqtSlot(str)
    def copy(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    @pyqtSlot(str)
    def openLink(self, url: str) -> None:
        target = QUrl(url)
        if target.scheme() in ("http", "https"):
            QDesktopServices.openUrl(target)

    @pyqtSlot(str)
    def expandDiagram(self, source: str) -> None:
        dialog = QDialog(self.view.window())
        dialog.setWindowTitle("Diagramma")
        dialog.resize(960, 700)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        diagram = ChatTranscript(dialog)
        layout.addWidget(diagram)
        diagram.set_payload({"diagram": source})
        dialog.setModal(True)
        dialog.show()


class ChatTranscript(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.browser: Optional[Any] = None
        self.ready = False
        self.payload: dict[str, Any] = {"messages": [], "answer": "", "busy": False}
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.placeholder = QLabel("✦\n\nLeggiamo insieme\n\nChiedi una spiegazione, un riassunto\no un esempio sul testo del PDF.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setStyleSheet("color: #92969d; font-size: 13px; padding: 18px; background: transparent;")
        self.layout_box.addWidget(self.placeholder, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.flush)

    def create_browser(self) -> None:
        global _interceptor
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        class LocalAssetsOnly(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info: Any) -> None:
                url = info.requestUrl()
                if url.scheme() in ("qrc", "data", "blob"):
                    return
                path = os.path.realpath(url.toLocalFile())
                root = os.path.realpath(assets_path())
                if url.scheme() != "file" or os.path.commonpath([path, root]) != root:
                    info.block(True)

        profile = QWebEngineProfile.defaultProfile()
        if profile is None:
            raise RuntimeError("Profilo della chat non disponibile")
        if _interceptor is None:
            _interceptor = LocalAssetsOnly(profile)
            profile.setUrlRequestInterceptor(_interceptor)
        browser = QWebEngineView(self)
        self.browser = browser
        page = browser.page()
        if page is None:
            raise RuntimeError("Pagina della chat non disponibile")
        page.setBackgroundColor(self.palette().window().color())
        self.channel = QWebChannel(page)
        self.bridge = ChatBridge(self)
        self.channel.registerObject("chat", self.bridge)
        page.setWebChannel(self.channel)
        browser.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        browser.loadFinished.connect(self.loaded)
        self.placeholder.hide()
        self.layout_box.addWidget(browser, 1)
        browser.load(QUrl.fromLocalFile(os.path.join(assets_path(), "index.html")))

    def loaded(self, success: bool) -> None:
        self.ready = success
        if success:
            self.flush()
        else:
            self.placeholder.setText("Non è stato possibile caricare la chat.")
            self.placeholder.show()

    def set_payload(self, payload: dict[str, Any]) -> None:
        force_scroll = bool(self.payload.get("forceScroll")) or bool(payload.get("forceScroll"))
        self.payload = dict(payload, forceScroll=force_scroll)
        if not payload.get("messages") and not payload.get("answer") and not payload.get("diagram"):
            if self.browser is not None:
                self.browser.hide()
            self.placeholder.show()
            return
        self.placeholder.hide()
        if self.browser is None:
            self.create_browser()
        else:
            self.browser.show()
        if self.ready and not self.timer.isActive():
            self.timer.start()

    def flush(self) -> None:
        if self.ready and self.browser is not None:
            self.browser.page().runJavaScript("window.renderChat(" + json.dumps(self.payload) + ");")
            self.payload["forceScroll"] = False

    def shutdown(self) -> None:
        self.timer.stop()
        if self.browser is not None:
            self.browser.stop()
