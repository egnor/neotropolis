"""Driver for pair of Trashbot "eye" displays"""

import json
import logging
import os
import subprocess
import sys

_log = logging.getLogger(__name__)


class DisplayError(Exception):
    pass


class EyeDisplayDriver:
    def __init__(self):
        self.eye_workers = []

        _log.info("🤓 Starting eye display workers...")
        for ei in range(2):
            worker_name = "trashbot.eye_display_worker"
            worker_args = [sys.executable, "-m", worker_name, f"--screen={ei}"]
            try:
                worker = subprocess.Popen(
                    worker_args,
                    bufsize=1,
                    env={**os.environ, "PYGAME_HIDE_SUPPORT_PROMPT": "1"},
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                )
            except subprocess.SubprocessError:
                raise DisplayError(f"Error starting eye {ei} worker")

            self.eye_workers.append(worker)

        for worker in self.eye_workers:
            try:
                ready_line = worker.stdout.readline()
            except (OSError, subprocess.SubprocessError):
                raise DisplayError(f"Error reading eye {ei} worker status")

            try:
                ready = json.loads(ready_line)
            except json.JSONDecodeError:
                raise DisplayError(f"Bad eye {ei} worker status: {ready_line}")

            if not isinstance(ready, dict) or not ready.get("ready"):
                raise DisplayError(f"Bad eye {ei} worker status: {ready}")

        _log.info("😎 Eye display workers ready")

    def set_display(self, eye: int, request: dict):
        worker = self.eye_workers[eye]
        try:
            worker.stdin.write(f"{json.dumps(request)}\n")
            worker.poll()
        except (OSError, subprocess.SubprocessError):
            raise DisplayError(f"Error sending eye {eye} worker command")

        if worker.returncode is not None:
            raise DisplayError(f"Eye {eye} worker died: {worker.returncode}")
