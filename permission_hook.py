import json
import os
import socket
import sys


def run_hook() -> int:
    decision = {"decision": "deny", "reason": "George non è disponibile per autorizzare l'operazione."}
    try:
        with os.fdopen(0) as source:
            tool = json.load(source).get("toolCall", {})
        request = {"token": os.environ["GEORGE_PERMISSION_TOKEN"], "toolCall": tool}
        socket_addr = os.environ["GEORGE_PERMISSION_SOCKET"]
        payload = (json.dumps(request) + "\n").encode()
        response = b""

        if sys.platform == "win32" or socket_addr.startswith("\\\\.\\pipe\\"):
            pipe_path = socket_addr if socket_addr.startswith("\\\\.\\pipe\\") else f"\\\\.\\pipe\\{os.path.basename(socket_addr)}"
            with open(pipe_path, "r+b", buffering=0) as pipe:
                pipe.write(payload)
                while b"\n" not in response and len(response) < 65536:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    response += chunk
        else:
            af_unix = getattr(socket, "AF_UNIX", 1)
            with socket.socket(af_unix, socket.SOCK_STREAM) as connection:
                connection.settimeout(120)
                connection.connect(socket_addr)
                connection.sendall(payload)
                while b"\n" not in response and len(response) < 65536:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    response += chunk

        result = json.loads(response)
        if isinstance(result, dict) and result.get("decision") in ("deny", "auto_approve", "allow"):
            decision = result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    os.write(1, (json.dumps(decision) + "\n").encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(run_hook())
