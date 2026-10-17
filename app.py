import sys

if __name__ == "__main__" and sys.argv[1:] == ["--permission-hook"]:
    from permission_hook import run_hook
    sys.exit(run_hook())

import traceback
from typing import Any

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMessageBox

import settings
from vault import VaultSelector
from window import MainWindow


def global_exception_handler(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    err_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("CRASH INTERCETTATO:", err_msg)
    QMessageBox.critical(None, "Errore Imprevisto (Crash Evitato)", f"Qualcosa è andato storto:\n{err_msg}")



def main() -> int:
    sys.excepthook = global_exception_handler
    settings.initialize()
    app = QApplication(sys.argv)
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))
    else:
        app.setFont(QFont(".AppleSystemUIFont", 13))
    app.setStyle("Fusion")
    selector = VaultSelector()
    if not selector.exec():
        return 0
    window = MainWindow(selector.selected_path, session=selector.resume_session)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
