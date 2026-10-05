"""tests/local_api_harness: start the VALUE local API for HTTP tests (C14).

``start_local_api(data_home=tmp)`` serves ``backend.server.Handler`` through
``backend.server.make_api_server`` on 127.0.0.1 with an OS-assigned port
(never 8766/8800) and a fresh session token, points every state root of
``backend.server`` at ``data_home``, publishes the session file under
``data_home/runtime/`` (so ``backend.api_session.authorized_headers(data_home,
port)`` works) and installs a urllib opener that adds only the
``X-VALUE-Session`` header to requests for this server.  It never adds an
``Origin`` header: the API rejects browser-originated requests that do not
come through the UI gateway (P0-1).  Everything is restored when the context
exits (opener, patches, session file, supervisor).

    with start_local_api(data_home=tmp) as (httpd, origin, token):
        ...

Tests that patch their own selection of state roots (some deliberately read
the repository's data packs) pass ``patch_state_roots=False``; the harness
then leaves every root alone, publishes no session file unless asked
(``publish=True``) and does not mount the data workbench unless asked.
Those tests that cannot use ``with`` call ``start()``/``stop()``::

    api = start_local_api(data_home=state, patch_state_roots=False)
    httpd, origin, token = api.start()
    try: ...
    finally: api.stop()

Interface fixed by P0_CONVENTIONS section 6 (P0-3 S7 minimal form, P0-1 S2
session token).
"""

from __future__ import annotations

import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
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
SESSION_HEADER = "X-VALUE-Session"


class _SessionHeaderProcessor(urllib.request.BaseHandler):
    """Adds the session header to requests for one origin; nothing else."""

    handler_order = 100

    def __init__(self, netloc: str, token: str | None) -> None:
        self.netloc = netloc
        self.token = token

    def http_request(self, request: urllib.request.Request) -> urllib.request.Request:
        if (
            self.token
            and urllib.parse.urlsplit(request.full_url).netloc == self.netloc
            and not request.has_header(SESSION_HEADER.capitalize())
        ):
            request.add_unredirected_header(SESSION_HEADER, self.token)
        return request


class LocalApi:
    def __init__(
        self,
        *,
        data_home: Path,
        token: str | None = None,
        patch_state_roots: bool = True,
        publish: bool | None = None,
        data_workbench: bool | None = None,
        install_opener: bool = True,
    ) -> None:
        self.data_home = Path(data_home)
        self.token = token
        self.patch_state_roots = patch_state_roots
        self.publish = patch_state_roots if publish is None else publish
        self.data_workbench = patch_state_roots if data_workbench is None else data_workbench
        self.install_opener = install_opener
        self.httpd: Any = None
        self.origin = ""
        self._patches: list[Any] = []
        self._thread: threading.Thread | None = None
        self._previous_opener: Any = None
        self._session_published = False

    # -- lifecycle -------------------------------------------------------
    def start(self) -> tuple[Any, str, str]:
        from backend import server
        from backend.api_session import new_token, publish_session

        if self.token is None:
            self.token = new_token()
        if self.patch_state_roots:
            from gridform_core.state_migrations import ensure_state_layout

            ensure_state_layout(self.data_home)
            self._patches = [
                patch.object(server, name, (self.data_home / relative) if relative else self.data_home)
                for name, relative in STATE_ROOT_NAMES.items()
            ]
        self._patches.append(patch.object(server, "SUPERVISOR", None))
        for item in self._patches:
            item.start()
        self._previous_opener = urllib.request._opener  # type: ignore[attr-defined]
        try:
            workbench = None
            if self.data_workbench:
                from backend.data_workbench_api import DataWorkbenchApi
                from gridform_core.data_workbench.jobs import SQLiteJobStore
                from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
                from gridform_core.data_workbench.state import resolve_data_workbench_root

                workbench_root = resolve_data_workbench_root(self.data_home)
                workbench = DataWorkbenchApi(
                    LocalDataWorkbenchService(workbench_root),
                    SQLiteJobStore(workbench_root / "jobs.sqlite"),
                )
            self.httpd = server.make_api_server(
                "127.0.0.1", 0, session_token=self.token, data_workbench_api=workbench,
            )
            port = int(self.httpd.server_address[1])
            if self.publish:
                publish_session(self.data_home, port, self.token)
                self._session_published = True
            self._thread = threading.Thread(target=self.httpd.serve_forever, name="local-api-harness", daemon=True)
            self._thread.start()
            self.origin = f"http://127.0.0.1:{port}"
            if self.install_opener:
                urllib.request.install_opener(
                    urllib.request.build_opener(_SessionHeaderProcessor(f"127.0.0.1:{port}", self.token))
                )
        except BaseException:
            self.stop()
            raise
        return self.httpd, self.origin, self.token

    def stop(self) -> None:
        from backend import server
        from backend.api_session import withdraw_session

        if self.install_opener:
            urllib.request.install_opener(self._previous_opener)
        if self.httpd is not None:
            if self._thread is not None:
                self.httpd.shutdown()
                self._thread.join(timeout=10)
            self.httpd.server_close()
            if self._session_published:
                withdraw_session(self.data_home, int(self.httpd.server_address[1]), str(self.token))
                self._session_published = False
            self.httpd = None
        supervisor = getattr(server, "SUPERVISOR", None)
        if supervisor is not None:
            supervisor.stop()
        for item in reversed(self._patches):
            item.stop()
        self._patches = []

    def __enter__(self) -> tuple[Any, str, str]:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def start_local_api(*, data_home: Path, token: str | None = None, **options: Any) -> LocalApi:
    """A ``LocalApi``; use it as a context manager or call ``start``/``stop``."""

    return LocalApi(data_home=data_home, token=token, **options)
