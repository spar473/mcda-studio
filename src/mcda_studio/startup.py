"""Local server readiness and lifetime library ownership; no numerical behaviour."""

import os
import socket
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Any

from mcda_studio.storage.library_backup import ensure_restore_complete


def run_server(application: Any, host: str, port: int, open_browser: bool) -> None:
    import uvicorn

    root = Path(application.state.store.root).expanduser()
    ensure_restore_complete(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root):
            pass
    except OSError as exc:
        raise ValueError(f"Cannot write project library {root}: {exc}") from exc
    address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
    sock = socket.socket(address[0], address[1], address[2])
    done = threading.Event()
    opener = None
    try:
        if os.name == "posix":
            # Rebind promptly over TIME_WAIT connections from a stopped server, as uvicorn does.
            # POSIX still refuses a port another socket is listening on; Windows reuse differs.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(address[4])
            sock.listen(socket.SOMAXCONN)
        except OSError as exc:
            raise ValueError(
                f"Cannot listen on {host}:{port}: {exc}. Choose another --port."
            ) from exc
        server = uvicorn.Server(
            uvicorn.Config(application, host=host, port=port, log_level="warning")
        )
        if open_browser:
            url_host = f"[{host}]" if ":" in host else host
            url = f"http://{url_host}:{sock.getsockname()[1]}"

            def open_when_ready() -> None:
                while not done.wait(0.05):
                    if server.started:
                        webbrowser.open(url)
                        return

            opener = threading.Thread(target=open_when_ready, daemon=True)
            opener.start()
        with application.state.store.ownership(port=sock.getsockname()[1]):
            server.run(sockets=[sock])
        if not server.started:
            raise ValueError("Server startup failed; the browser was not opened.")
    finally:
        done.set()
        sock.close()
        if opener:
            opener.join(timeout=1)
