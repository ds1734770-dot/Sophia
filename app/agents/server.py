"""
The local server agents report to. It listens only on this computer
(127.0.0.1) and every request must carry Sophia's secret token, so a web
page cannot send fake task updates.

    POST /event   {agent, status, title, message, question, task, project}
    GET  /answer?task=ID&wait=SECONDS    waits for the user's reply
    GET  /health

The port and token live in data/agent_hub.json, where the notify command
finds them.
"""

import hmac
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("sophia.agents")

DEFAULT_PORT = 47615
MAX_BODY = 64 * 1024
MAX_WAIT = 600
INFO_NAME = "agent_hub.json"


def load_or_create_token(path):
    """
    The secret shared with the notify command; created once.
    """

    try:

        token = json.loads(path.read_text(encoding="utf-8")).get("token")

        if token:
            return token

    except (OSError, ValueError):
        pass

    return secrets.token_urlsafe(32)


class AgentServer:

    def __init__(self, hub, data_dir, port=DEFAULT_PORT):

        self.hub = hub
        self.data_dir = data_dir
        self.preferred_port = port

        self.info_path = data_dir / INFO_NAME
        self.token = load_or_create_token(self.info_path)

        self.port = None
        self._server = None
        self._thread = None

    # ------------------------------------------------

    def start(self):
        """
        Start listening (tries a few ports if the first is taken).
        Returns the port.
        """

        handler = self._handler()

        last_error = None

        for offset in range(10):

            try:

                self._server = ThreadingHTTPServer(
                    ("127.0.0.1", self.preferred_port + offset), handler
                )

                break

            except OSError as e:
                last_error = e

        else:
            raise last_error

        self._server.daemon_threads = True

        self.port = self._server.server_address[1]

        self._write_info()

        self._thread = threading.Thread(
            target=self._server.serve_forever, name="agent-hub", daemon=True
        )

        self._thread.start()

        log.info("Agent hub listening on 127.0.0.1:%s", self.port)

        return self.port

    def stop(self):

        if self._server is not None:

            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _write_info(self):

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.info_path.write_text(
            json.dumps({"port": self.port, "token": self.token}),
            encoding="utf-8",
        )

    # ------------------------------------------------

    def _handler(self):

        server = self

        class Handler(BaseHTTPRequestHandler):

            def log_message(self, *args):
                pass

            def _reply(self, code, body):

                data = json.dumps(body).encode("utf-8")

                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()

                self.wfile.write(data)

            def _allowed(self):
                """
                A web page in a browser is never allowed, whatever token
                it has: only programs (no Origin) and browser extensions.
                """

                origin = self.headers.get("Origin", "")

                if origin and not origin.startswith(("chrome-extension://", "moz-extension://")):
                    return False

                given = self.headers.get("X-Sophia-Token", "")

                if not given:

                    auth = self.headers.get("Authorization", "")

                    given = auth[7:] if auth.startswith("Bearer ") else ""

                return hmac.compare_digest(given.encode(), server.token.encode())

            def do_GET(self):

                url = urlparse(self.path)

                if url.path == "/health":

                    self._reply(200, {"ok": True})

                    return

                if not self._allowed():

                    self._reply(401, {"error": "unauthorized"})

                    return

                if url.path == "/answer":

                    query = parse_qs(url.query)

                    task = (query.get("task") or [""])[0]

                    try:
                        wait = min(float((query.get("wait") or ["0"])[0]), MAX_WAIT)

                    except ValueError:
                        wait = 0.0

                    self._reply(200, {"answer": server.hub.wait_answer(task, wait)})

                    return

                self._reply(404, {"error": "not found"})

            def do_POST(self):

                try:
                    length = int(self.headers.get("Content-Length", "0"))

                except ValueError:
                    length = 0

                # always read what was sent: replying without reading it
                # makes the connection reset on Windows
                raw = self.rfile.read(length) if 0 < length <= MAX_BODY else b""

                if urlparse(self.path).path != "/event":

                    self._reply(404, {"error": "not found"})

                    return

                if not self._allowed():

                    self._reply(401, {"error": "unauthorized"})

                    return

                if not raw:

                    self._reply(413, {"error": "bad size"})

                    return

                try:
                    event = json.loads(raw.decode("utf-8"))

                except (ValueError, UnicodeDecodeError):

                    self._reply(400, {"error": "bad json"})

                    return

                task = server.hub.update(event)

                if task is None:

                    self._reply(400, {"error": "need a status: running, needs_input, done or failed"})

                    return

                self._reply(200, {"ok": True, "task": task.id})

        return Handler
