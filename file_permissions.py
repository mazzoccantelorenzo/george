import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QProcessEnvironment, Qt, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QMessageBox, QWidget


class FilePermissionGate(QObject):
    asking = pyqtSignal(bool)

    def __init__(self, workspace: Path, parent: QWidget) -> None:
        super().__init__(parent)
        self.widget = parent
        self.workspace = workspace.resolve()
        self.directory: Optional[tempfile.TemporaryDirectory] = None
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.accept_connections)
        self.buffers: dict[QLocalSocket, bytes] = {}
        self.token = secrets.token_hex(32)

    def prepare(self) -> QProcessEnvironment:
        if not self.directory:
            self.directory = tempfile.TemporaryDirectory(prefix="george-permissions-")
            address = os.path.join(self.directory.name, "gate")
            if not self.server.listen(address):
                self.close()
                raise OSError("Impossibile avviare la richiesta di autorizzazione: " + self.server.errorString())
        else:
            address = self.server.fullServerName()
        command = [sys.executable, "--permission-hook"] if getattr(sys, "frozen", False) else [
            sys.executable, str(Path(__file__).with_name("permission_hook.py"))]
        cmd_str = subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command)
        hooks = {"george-file-approval": {"PreToolUse": [{
            "matcher": "write_to_file|replace_file_content|multi_replace_file_content|run_command|notebook_edit|notebook_execution|sed_file|send_command_input",
            "hooks": [{"type": "command", "command": cmd_str, "timeout": 125}],
        }]}}
        directory = self.workspace / ".agents"
        directory.mkdir(exist_ok=True)
        (directory / "hooks.json").write_text(json.dumps(hooks))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("GEORGE_PERMISSION_SOCKET", address)
        environment.insert("GEORGE_PERMISSION_TOKEN", self.token)
        return environment

    def accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            if connection:
                self.buffers[connection] = b""
                connection.readyRead.connect(lambda socket=connection: self.read_request(socket))
                connection.disconnected.connect(lambda socket=connection: self.discard(socket))
                self.read_request(connection)

    def discard(self, connection: QLocalSocket) -> None:
        self.buffers.pop(connection, None)
        connection.deleteLater()

    def read_request(self, connection: QLocalSocket) -> None:
        data = self.buffers.get(connection, b"") + connection.readAll().data()
        self.buffers[connection] = data
        if len(data) > 2_000_000:
            connection.disconnectFromServer()
            return
        if b"\n" not in data:
            return
        result = {"decision": "deny", "reason": "Autorizzazione non valida."}
        try:
            request = json.loads(data.split(b"\n", 1)[0])
            if secrets.compare_digest(request.get("token", ""), self.token):
                tool = request.get("toolCall")
                if isinstance(tool, dict):
                    self.asking.emit(True)
                    try:
                        result = self.authorize(tool)
                    finally:
                        self.asking.emit(False)
        except (ValueError, TypeError, AttributeError):
            pass
        if connection.state() == QLocalSocket.LocalSocketState.ConnectedState:
            connection.write((json.dumps(result) + "\n").encode())
            connection.flush()
            connection.disconnectFromServer()

    def authorize(self, tool: dict) -> dict[str, str]:
        args = tool.get("args", {})
        if not isinstance(args, dict):
            return {"decision": "deny", "reason": "Operazione non valida."}
        name = tool.get("name")
        target = args.get("TargetFile") or args.get("AbsolutePath") or args.get("NotebookPath")
        if name in ("write_to_file", "replace_file_content", "multi_replace_file_content", "notebook_edit", "sed_file"):
            if not isinstance(target, str) or not target:
                return {"decision": "deny", "reason": "Percorso del file non specificato."}
            path = Path(target)
            path = (path if path.is_absolute() else self.workspace / path).resolve()
            if path == self.workspace / ".agents" or self.workspace / ".agents" in path.parents:
                return {"decision": "deny", "reason": "I controlli di autorizzazione di George non possono essere modificati dalla chat."}
            text = f"Antigravity vuole scrivere questo file:\n{path}"
            details = args.get("CodeContent") or json.dumps(args, ensure_ascii=False, indent=2)
        else:
            text = "Antigravity vuole eseguire un'operazione che può modificare file."
            details = json.dumps(args, ensure_ascii=False, indent=2)
        dialog = QMessageBox(self.widget)
        dialog.setWindowTitle("Autorizza Antigravity")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        dialog.setInformativeText("Apri i dettagli per vedere la modifica. La scelta vale solo per questa operazione.")
        dialog.setDetailedText(str(details))
        allow = dialog.addButton("Consenti", QMessageBox.ButtonRole.AcceptRole)
        deny = dialog.addButton("Nega", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(deny)
        dialog.setEscapeButton(deny)
        dialog.exec()
        approved = dialog.clickedButton() is allow
        return {"decision": "auto_approve" if approved else "deny",
            "reason": "Operazione autorizzata dall'utente in George." if approved else "Operazione rifiutata dall'utente in George."}

    def close(self) -> None:
        self.server.close()
        for connection in list(self.buffers):
            connection.disconnectFromServer()
        if self.directory:
            self.directory.cleanup()
            self.directory = None
