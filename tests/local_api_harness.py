"""tests/local_api_harness: start the VALUE local API for HTTP tests (C14).

``start_local_api(data_home=tmp)`` serves ``backend.server.Handler`` on
127.0.0.1 with an OS-assigned port (never 8766/8800), points every state root
of ``backend.server`` at ``data_home`` and installs a urllib opener that adds
the Host/Origin headers (and, once P0-1 S2 issues one, the session token).
Everything is restored when the context exits.

    with start_local_api(data_home=tmp) as (httpd, origin, token):
        ...

Interface fixed by P0_CONVENTIONS section 6.  P0-3 S7 introduced this minimal
form for its HTTP tests; P0-1 S2 extends it with the session token.
"""

from __future__ import annotations

import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

STATE_ROOT_NAMES = {
    "STATE_ROOT": "",
    "PACKS_ROOT": "data-packs",
    "PROJECTS_ROOT": "projects",
    "RUNS_ROOT": "runs",
    "OBJECTS_ROOT": "objects/sha256",
    "IMPORT_STAGING_ROOT": "import-staging",
    "ARCHIVES_ROOT": "archives",
    "TRASH_ROOT": "trash",
}


class _HeaderProcessor(urllib.request.BaseHandler):
    handler_order = 100

    def __init__(self, token: str | None) -> None:
        self.token = token

    def http_request(self, request: urllib.request.Request) -> urllib.request.Request:
        if not request.has_header("Origin"):
            request.add_unredirected_header("Origin", "http://127.0.0.1:18800")
        if self.token and not request.has_header("X-value-session"):
            request.add_unredirected_header("X-VALUE-Session", self.token)
        return request


@contextmanager
def start_local_api(*, data_home: Path, token: str | None = None) -> Iterator[tuple[object, str, str | None]]:
    from http.server import ThreadingHTTPServer

    from backend import server
    from gridform_core.state_migrations import ensure_state_layout

    data_home = Path(data_home)
    ensure_state_layout(data_home)
    patches = [
        patch.object(server, name, (data_home / relative) if relative else data_home)
        for name, relative in STATE_ROOT_NAMES.items()
    ]
    patches.append(patch.object(server, "SUPERVISOR", None))
    for item in patches:
        item.start()
    httpd = None
    previous_opener = urllib.request._opener  # type: ignore[attr-defined]
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        from backend.data_workbench_api import DataWorkbenchApi
        from gridform_core.data_workbench.jobs import SQLiteJobStore
        from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
        from gridform_core.data_workbench.state import resolve_data_workbench_root

        workbench_root = resolve_data_workbench_root(data_home)
        httpd.data_workbench_api = DataWorkbenchApi(  # type: ignore[attr-defined]
            LocalDataWorkbenchService(workbench_root),
            SQLiteJobStore(workbench_root / "jobs.sqlite"),
        )
        thread = threading.Thread(target=httpd.serve_forever, name="local-api-harness", daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{httpd.server_address[1]}"
        urllib.request.install_opener(urllib.request.build_opener(_HeaderProcessor(token)))
        yield httpd, origin, token
    finally:
        urllib.request.install_opener(previous_opener)
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        supervisor = getattr(server, "SUPERVISOR", None)
        if supervisor is not None:
            supervisor.stop()
        for item in reversed(patches):
            item.stop()
