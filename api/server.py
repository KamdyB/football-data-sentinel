from __future__ import annotations

import json
import logging
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import (
    urlparse,
)

from pipeline import (
    build_orchestrator,
)

from storage.runs import (
    SQLiteRunRepository,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "sentinel.api"
)

MAX_BODY_BYTES = (
    5 * 1024 * 1024
)

repository = (
    SQLiteRunRepository()
)

orchestrator = (
    build_orchestrator()
)


class SentinelHandler(
    BaseHTTPRequestHandler
):

    def log_message(
        self,
        format: str,
        *args,
    ) -> None:

        logger.info(
            "%s - %s",
            self.address_string(),
            format % args,
        )

    def _send(
        self,
        status: int,
        payload: dict,
    ) -> None:

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_OPTIONS(self) -> None:

        self.send_response(204)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.end_headers()

    def do_GET(self) -> None:

        path = urlparse(
            self.path
        ).path

        if path == "/health":

            self._send(
                200,
                {
                    "service":
                        "football-data-sentinel",
                    "status": "ok",
                },
            )

            return

        if path == "/api/runs/latest":

            report = (
                repository.latest()
            )

            if report:
                self._send(
                    200,
                    report,
                )
            else:
                self._send(
                    404,
                    {
                        "error":
                            "no runs available"
                    },
                )

            return

        if path == "/api/runs":

            self._send(
                200,
                {
                    "runs":
                        repository.history(
                            limit=25
                        )
                },
            )

            return

        parts = (
            path.rstrip("/")
            .split("/")
        )

        if (
            len(parts) == 4
            and parts[:3]
            == [
                "",
                "api",
                "runs",
            ]
        ):

            report = (
                repository.get(
                    parts[3]
                )
            )

            if report:
                self._send(
                    200,
                    report,
                )
            else:
                self._send(
                    404,
                    {
                        "error":
                            "run not found"
                    },
                )

            return

        self._send(
            404,
            {
                "error":
                    "route not found"
            },
        )

    def do_POST(self) -> None:

        if (
            urlparse(
                self.path
            ).path
            != "/api/run"
        ):

            self._send(
                404,
                {
                    "error":
                        "route not found"
                },
            )

            return

        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )
        except ValueError:

            self._send(
                400,
                {
                    "error":
                        "invalid Content-Length"
                },
            )

            return

        if length > MAX_BODY_BYTES:

            self._send(
                413,
                {
                    "error":
                        "payload too large"
                },
            )

            return

        payload = None

        if length:

            try:

                payload = json.loads(
                    self.rfile.read(
                        length
                    ).decode(
                        "utf-8"
                    )
                )

            except json.JSONDecodeError:

                self._send(
                    400,
                    {
                        "error":
                            "request body is "
                            "not valid JSON"
                    },
                )

                return

            if not isinstance(
                payload,
                dict,
            ):

                self._send(
                    400,
                    {
                        "error":
                            "request body must "
                            "be a JSON object"
                    },
                )

                return

        try:

            report = (
                orchestrator.run(
                    payload
                )
            )

            self._send(
                200,
                report,
            )

        except (
            ValueError,
            TypeError,
            FileNotFoundError,
        ) as exc:

            logger.warning(
                "pipeline rejected request: %s",
                exc,
            )

            self._send(
                400,
                {
                    "error":
                        str(exc)
                },
            )

        except Exception:

            logger.exception(
                "pipeline execution failed"
            )

            self._send(
                500,
                {
                    "error":
                        "internal pipeline failure"
                },
            )


if __name__ == "__main__":

    logger.info(
        "Sentinel API listening "
        "on 0.0.0.0:8080"
    )

    ThreadingHTTPServer(
        (
            "0.0.0.0",
            8080,
        ),
        SentinelHandler,
    ).serve_forever()