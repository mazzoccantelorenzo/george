import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import settings
from resources import get_resource_path


@dataclass
class UpdateReleaseInfo:
    version: str
    tag_name: str
    title: str
    release_notes: str
    html_url: str
    download_url: Optional[str]
    asset_name: Optional[str]
    asset_size: int = 0


def parse_version(ver_str: str) -> tuple[int, ...]:
    """Converte stringhe come 'v12.0', '12.1.2', 'v13.0-rc1' in una tupla di interi per il confronto."""
    numbers = [int(n) for n in re.findall(r"\d+", ver_str)]
    return tuple(numbers) if numbers else (0,)


def is_newer_version(latest_str: str, current_str: str) -> bool:
    """Verifica se latest_str è strettamente più recente di current_str."""
    latest = parse_version(latest_str)
    current = parse_version(current_str)
    max_len = max(len(latest), len(current))
    latest_padded = latest + (0,) * (max_len - len(latest))
    current_padded = current + (0,) * (max_len - len(current))
    return latest_padded > current_padded


def get_current_bundle_path() -> Optional[str]:
    """Trova il percorso del bundle George.app (macOS) o della cartella di installazione (Windows)."""
    if sys.platform == "win32":
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        local_programs = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
            "Programs",
            "George",
        )
        if os.path.isdir(local_programs):
            return local_programs
        desktop_win = os.path.expanduser("~/Desktop/George")
        if os.path.isdir(desktop_win):
            return desktop_win
        return None

    if getattr(sys, "frozen", False):
        path = os.path.abspath(sys.executable)
        while path and path != "/":
            if path.endswith(".app"):
                return path
            path = os.path.dirname(path)

    # Fallback ai percorsi standard macOS
    system_app = "/Applications/George.app"
    if os.path.isdir(system_app):
        return system_app
    desktop_app = os.path.expanduser("~/Desktop/George.app")
    if os.path.isdir(desktop_app):
        return desktop_app
    return None


def select_platform_asset(
    assets: list[dict[str, object]],
    platform: str = sys.platform,
) -> tuple[Optional[str], Optional[str], int]:
    """Seleziona l'asset ZIP corretto dalla release GitHub in base al sistema operativo (Windows vs macOS)."""
    is_win = platform == "win32"

    def _extract_info(asset: dict[str, object]) -> tuple[Optional[str], Optional[str], int]:
        url = asset.get("browser_download_url")
        name = asset.get("name")
        size = asset.get("size")
        return (
            url if isinstance(url, str) else None,
            name if isinstance(name, str) else None,
            size if isinstance(size, int) else 0,
        )

    if is_win:
        # 1. Cerca uno zip specifico per Windows (es. George-Windows.zip)
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip") and ("win" in name or "windows" in name):
                return _extract_info(asset)
        # 2. Cerca un eseguibile .exe (se distribuito come singolo file)
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".exe") and "george" in name:
                return _extract_info(asset)
        # 3. Fallback: qualsiasi zip che non sia esplicitamente per Mac
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip") and not any(m in name for m in ("mac", "darwin", "osx")):
                return _extract_info(asset)
    else:
        # 1. Cerca uno zip per macOS o il classico George.zip (escludendo i pacchetti Windows)
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip") and "george" in name and "win" not in name:
                return _extract_info(asset)
        # 2. Fallback: primo zip non-Windows disponibile
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip") and "win" not in name:
                return _extract_info(asset)

    return None, None, 0


class UpdateCheckThread(QThread):
    """Thread di background per il controllo asincrono di nuove versioni senza bloccare la UI."""
    update_available = pyqtSignal(object)  # UpdateReleaseInfo
    already_latest = pyqtSignal(str)       # current version
    check_failed = pyqtSignal(str)         # error message

    def __init__(self, repo: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(None)
        self.repo = repo
        self._parent = parent

    def run(self) -> None:
        api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": f"George-App/{settings.APP_VERSION}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    self.check_failed.emit(f"Server ha risposto con codice {response.status}")
                    return
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            if not tag_name:
                self.check_failed.emit("Nessun tag versione trovato nella release remota.")
                return

            if not is_newer_version(tag_name, settings.APP_VERSION):
                self.already_latest.emit(settings.APP_VERSION)
                return

            raw_assets = data.get("assets", [])
            assets_list = raw_assets if isinstance(raw_assets, list) else []
            download_url, asset_name, asset_size = select_platform_asset(assets_list)

            release_info = UpdateReleaseInfo(
                version=tag_name,
                tag_name=tag_name,
                title=data.get("name") or tag_name,
                release_notes=data.get("body") or "Nessuna nota di rilascio fornita.",
                html_url=data.get("html_url", f"https://github.com/{self.repo}/releases"),
                download_url=download_url,
                asset_name=asset_name,
                asset_size=asset_size,
            )
            self.update_available.emit(release_info)

        except urllib.error.URLError as err:
            self.check_failed.emit(f"Connessione a GitHub fallita: {err.reason}")
        except Exception as err:
            self.check_failed.emit(f"Errore durante la verifica: {err}")


class UpdateDownloadThread(QThread):
    """Thread di background per il download e l'estrazione dell'aggiornamento (macOS e Windows)."""
    progress = pyqtSignal(int, int)        # bytes_read, total_bytes
    download_complete = pyqtSignal(str, str)  # extracted_app_path, temp_dir
    download_failed = pyqtSignal(str)

    def __init__(self, download_url: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(None)
        self.download_url = download_url
        self._parent = parent
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        temp_dir = tempfile.mkdtemp(prefix="george_update_")
        is_direct_exe = sys.platform == "win32" and self.download_url.lower().endswith(".exe")
        archive_path = os.path.join(temp_dir, "George.exe" if is_direct_exe else "George_update.zip")
        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": f"George-App/{settings.APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_bytes = int(resp.headers.get("Content-Length", 0))
                downloaded_bytes = 0
                chunk_size = 64 * 1024

                with open(archive_path, "wb") as f_out:
                    while True:
                        if self._is_cancelled:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            self.download_failed.emit("Download annullato dall'utente.")
                            return
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded_bytes += len(chunk)
                        self.progress.emit(downloaded_bytes, total_bytes)

            if is_direct_exe:
                self.download_complete.emit(archive_path, temp_dir)
                return

            # Estrai lo ZIP (su macOS usa /usr/bin/ditto per preservare i symlink .framework)
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            if sys.platform == "darwin" and os.path.exists("/usr/bin/ditto"):
                subprocess.run(
                    ["/usr/bin/ditto", "-x", "-k", archive_path, extract_dir],
                    check=True,
                )
            else:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(extract_dir)

            target_app: Optional[str] = None
            if sys.platform == "win32":
                # Su Windows cerca la cartella che contiene George.exe
                for root, _, files in os.walk(extract_dir):
                    for f_name in files:
                        if f_name.lower() == "george.exe":
                            target_app = root
                            break
                    if target_app:
                        break
            else:
                # Su macOS cerca George.app all'interno della cartella estratta
                for root, dirs, _ in os.walk(extract_dir):
                    for d in dirs:
                        if d.endswith(".app") and "george" in d.lower():
                            target_app = os.path.join(root, d)
                            break
                    if target_app:
                        break

            if not target_app:
                shutil.rmtree(temp_dir, ignore_errors=True)
                expected = "George.exe" if sys.platform == "win32" else "George.app"
                self.download_failed.emit(f"Nessun pacchetto {expected} trovato nell'archivio scaricato.")
                return

            self.download_complete.emit(target_app, temp_dir)

        except Exception as err:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.download_failed.emit(f"Download non riuscito: {err}")


def apply_update_and_restart(new_app_path: str, temp_dir: str) -> None:
    """Sostituisce l'applicazione corrente (su Windows o macOS) e la riavvia automaticamente."""
    current_app = get_current_bundle_path()

    if sys.platform == "win32":
        if not current_app:
            current_app = os.path.join(
                os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
                "Programs",
                "George",
            )
        target_exe = os.path.join(current_app, "George.exe")
        bat_path = os.path.join(temp_dir, "swap_and_restart.bat")
        bat_content = f"""@echo off
set OLD_PID={os.getpid()}
set "NEW_APP={new_app_path}"
set "TARGET_DIR={current_app}"
set "TARGET_EXE={target_exe}"
set "TEMP_DIR={temp_dir}"

:waitloop
tasklist /FI "PID eq %OLD_PID%" 2>NUL | find /I "%OLD_PID%" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >NUL
    goto waitloop
)

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

if exist "%NEW_APP%\\George.exe" (
    robocopy "%NEW_APP%" "%TARGET_DIR%" /E /IS /IT /NFL /NDL /NJH /NJS /NC /NS /NP >NUL
) else (
    copy /Y "%NEW_APP%" "%TARGET_EXE%" >NUL
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%TARGET_DIR%' -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >NUL 2>&1

start "" "%TARGET_EXE%"
rmdir /S /Q "%TEMP_DIR%" >NUL 2>&1
"""
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # DETACHED_PROCESS (0x08) | CREATE_NEW_PROCESS_GROUP (0x200) | CREATE_NO_WINDOW (0x08000000)
        creation_flags = 0x00000008 | 0x00000200 | 0x08000000
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=creation_flags,
            close_fds=True,
        )
    else:
        if not current_app:
            current_app = os.path.expanduser("~/Desktop/George.app")

        script_path = os.path.join(temp_dir, "swap_and_restart.sh")
        script_content = f"""#!/bin/bash
set -e

OLD_PID="{os.getpid()}"
NEW_APP="{new_app_path}"
TARGET_APP="{current_app}"
TEMP_DIR="{temp_dir}"

# Attendi che il vecchio processo di George termini
while kill -0 "$OLD_PID" 2>/dev/null; do
    sleep 0.2
done

sleep 0.3

# Backup dell'app corrente in caso di problemi
BACKUP_APP="${{TARGET_APP}}.bak"
rm -rf "$BACKUP_APP"
if [ -d "$TARGET_APP" ]; then
    cp -R "$TARGET_APP" "$BACKUP_APP" 2>/dev/null || true
fi

# Sostituisci il bundle dell'app
rm -rf "$TARGET_APP"
mv "$NEW_APP" "$TARGET_APP"

# Rimuovi gli attributi di quarantena e ri-firma ad-hoc per evitare blocchi Gatekeeper su Apple Silicon
xattr -cr "$TARGET_APP" 2>/dev/null || true
codesign --force --deep --sign - "$TARGET_APP" 2>/dev/null || true

# Pulisci backup e file temporanei
rm -rf "$BACKUP_APP"
rm -rf "$TEMP_DIR"

# Riavvia George aggiornato
open "$TARGET_APP"
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)

        # Lancia lo script in un nuovo processo indipendente
        subprocess.Popen(["/bin/bash", script_path], start_new_session=True)

    # Chiudi l'applicazione corrente in modo pulito
    app = QApplication.instance()
    if app:
        app.quit()
    sys.exit(0)


class UpdateDialog(QDialog):
    """Finestra di dialogo moderna dark-themed per notificare e applicare gli aggiornamenti."""

    def __init__(self, release_info: UpdateReleaseInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.release_info = release_info
        self.download_thread: Optional[UpdateDownloadThread] = None

        self.setWindowTitle("Aggiornamento Software — George")
        self.setMinimumWidth(520)
        self.resize(540, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #cccccc;
            }
            QTextBrowser {
                background-color: #252525;
                color: #e0e0e0;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
            }
            QProgressBar {
                background-color: #2d2d2d;
                border: 1px solid #444444;
                border-radius: 6px;
                text-align: center;
                color: white;
                font-weight: bold;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #7a5cfa;
                border-radius: 5px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header con versione
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        icon_path = get_resource_path("icons/download.svg")
        if os.path.exists(icon_path):
            header_icon.setPixmap(QIcon(icon_path).pixmap(32, 32))
        header_layout.addWidget(header_icon)

        title_box = QVBoxLayout()
        title_label = QLabel("Nuovo aggiornamento disponibile!")
        title_font = QFont(".AppleSystemUIFont", 16, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #ffffff;")

        version_label = QLabel(f"Versione corrente: {settings.APP_VERSION}  ➔  Nuova versione: <b>{release_info.version}</b>")
        version_label.setStyleSheet("color: #a78bfa; font-size: 13px;")

        title_box.addWidget(title_label)
        title_box.addWidget(version_label)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Note di rilascio
        notes_title = QLabel("Cosa c'è di nuovo:")
        notes_title.setStyleSheet("color: #aaaaaa; font-weight: bold; font-size: 12px; text-transform: uppercase;")
        layout.addWidget(notes_title)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setMarkdown(release_info.release_notes)
        layout.addWidget(self.notes_browser)

        # Barra di progresso download (inizialmente nascosta)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Pulsanti azione
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_later = QPushButton("Più tardi")
        self.btn_later.setStyleSheet("background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 7px 16px;")
        self.btn_later.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_later)

        self.btn_update = QPushButton("Aggiorna ora")
        self.btn_update.setStyleSheet("background-color: #7a5cfa; border-color: #7a5cfa; color: white; padding: 7px 20px; font-weight: bold;")
        self.btn_update.clicked.connect(self.start_update)
        btn_layout.addWidget(self.btn_update)

        layout.addLayout(btn_layout)

    def start_update(self) -> None:
        if not self.release_info.download_url:
            QMessageBox.warning(
                self,
                "Download non disponibile",
                f"Nessun pacchetto zip è allegato a questa release.\nVisita: {self.release_info.html_url}",
            )
            return

        self.btn_update.setEnabled(False)
        self.btn_later.setText("Annulla")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Download aggiornamento in corso...")

        self.download_thread = UpdateDownloadThread(self.release_info.download_url, self)
        self.download_thread.progress.connect(self.on_download_progress)
        self.download_thread.download_complete.connect(self.on_download_complete)
        self.download_thread.download_failed.connect(self.on_download_failed)
        self.download_thread.start()

    def on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            mb_down = downloaded / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            self.status_label.setText(f"Download: {mb_down:.1f} MB di {mb_tot:.1f} MB ({pct}%)")
        else:
            self.progress_bar.setMaximum(0)  # indeterminate
            mb_down = downloaded / (1024 * 1024)
            self.status_label.setText(f"Scaricati: {mb_down:.1f} MB")

    def on_download_complete(self, target_app: str, temp_dir: str) -> None:
        self.status_label.setText("Download completato! Riavvio in corso...")
        self.progress_bar.setValue(100)
        apply_update_and_restart(target_app, temp_dir)

    def on_download_failed(self, error_msg: str) -> None:
        self.status_label.setText("Errore durante il download.")
        self.progress_bar.setVisible(False)
        self.btn_update.setEnabled(True)
        self.btn_later.setText("Chiudi")
        QMessageBox.critical(self, "Aggiornamento Fallito", f"Impossibile completare l'aggiornamento:\n{error_msg}")

    def reject(self) -> None:
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait(1000)
        super().reject()


# Controller globale per lanciare la verifica degli aggiornamenti
_active_check_thread: Optional[UpdateCheckThread] = None


def _is_widget_alive(w: Optional[QWidget]) -> bool:
    if w is None:
        return False
    try:
        from PyQt6 import sip
        return not sip.isdeleted(w)
    except Exception:
        return True


def check_updates(
    parent: Optional[QWidget] = None,
    silent_if_latest: bool = False,
    on_available: Optional[Callable[[UpdateReleaseInfo], None]] = None,
) -> None:
    """Verifica la disponibilità di aggiornamenti in background.

    - Se silent_if_latest=True: non mostra alcun popup se George è già all'ultima versione (ideale all'avvio).
    - Se silent_if_latest=False: mostra conferma all'utente se non ci sono aggiornamenti (ideale per click manuale).
    """
    global _active_check_thread

    repo = getattr(settings, "UPDATE_REPO", "mazzoccantelorenzo/george")
    if not repo:
        if not silent_if_latest:
            target_parent = parent if _is_widget_alive(parent) else None
            QMessageBox.information(
                target_parent,
                "Aggiornamenti Disabilitati",
                "Nessun repository GitHub configurato per la ricerca degli aggiornamenti.",
            )
        return

    # Evita di sovrapporre controlli multipli
    if _active_check_thread is not None and _active_check_thread.isRunning():
        return

    _active_check_thread = UpdateCheckThread(repo, parent)

    def on_update_found(release_info: UpdateReleaseInfo) -> None:
        if on_available is not None:
            on_available(release_info)
        target_parent = parent if _is_widget_alive(parent) else None
        dialog = UpdateDialog(release_info, target_parent)
        dialog.exec()

    def on_already_latest(current_ver: str) -> None:
        if not silent_if_latest:
            target_parent = parent if _is_widget_alive(parent) else None
            QMessageBox.information(
                target_parent,
                "George è Aggiornato",
                f"Stai già utilizzando l'ultima versione disponibile ({current_ver}).",
            )

    def on_check_failed(err_msg: str) -> None:
        if not silent_if_latest:
            target_parent = parent if _is_widget_alive(parent) else None
            QMessageBox.warning(
                target_parent,
                "Controllo Aggiornamenti Fallito",
                f"Impossibile verificare la presenza di aggiornamenti:\n{err_msg}",
            )

    _active_check_thread.update_available.connect(on_update_found)
    _active_check_thread.already_latest.connect(on_already_latest)
    _active_check_thread.check_failed.connect(on_check_failed)
    _active_check_thread.start()
