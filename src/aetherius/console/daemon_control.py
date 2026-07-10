"""Manage the local daemon as a child process, on behalf of the Console.

The Console can start and stop ``aetherius serve`` without leaving the terminal. The daemon runs as a
separate process (``python -m aetherius serve``) so it can be killed cleanly and, deliberately,
survives navigating away from the Settings screen — it is a service, not a screen's state. It is
owned by the App (one per session) and stopped on exit, with an ``atexit`` guard against orphans.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys

from ..server.config import DaemonConfig


class DaemonController:
    """Start, stop and probe a local daemon child process."""

    def __init__(self) -> None:
        self._config = DaemonConfig()
        self._process: subprocess.Popen[bytes] | None = None
        atexit.register(self.stop)

    @property
    def config(self) -> DaemonConfig:
        return self._config

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Spawn the daemon with the resolved config. No-op if already running."""
        if self.is_running():
            return
        # The token is passed through the environment, never argv, so it does not leak into `ps`.
        env = dict(os.environ)
        if self._config.token:
            env["AETHERIUS_DAEMON_TOKEN"] = self._config.token
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "aetherius",
                "serve",
                "--host",
                self._config.host,
                "--port",
                str(self._config.port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        """Terminate the daemon if running. Idempotent."""
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self._process = None

    def healthy(self) -> bool:
        """True if the daemon answers its health probe. Never raises."""
        import httpx

        try:
            response = httpx.get(f"{self.base_url}/health", timeout=1.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
