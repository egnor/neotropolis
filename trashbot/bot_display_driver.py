"""Driver for pair of Trashbot "eye" displays"""

import json
import logging
import os
import subprocess
import sys

_log = logging.getLogger(__name__)


class DisplayError(Exception):
    pass


class BotDisplayDriver:
    def __init__(self):
        self.eye_workers = []

        _log.info('🤓 Starting "eye" display workers...')
        for ei in range(2):
            worker_name = "trashbot.bot_display_worker"
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

            if not ready_line.strip():
                raise DisplayError(f"Empty output from eye {ei} worker")

            try:
                ready = json.loads(ready_line)
            except json.JSONDecodeError:
                raise DisplayError(f"Bad eye {ei} worker status: {ready_line}")

            if not isinstance(ready, dict) or not ready.get("ready"):
                raise DisplayError(f"Bad eye {ei} worker status: {ready}")

        _log.info("😎 Display workers ready")

    def set_display(self, eye: int, request: dict):
        worker = self.eye_workers[eye]
        try:
            worker.poll()
            worker.stdin.write(f"{json.dumps(request)}\n")
        except BrokenPipeError:
            # don't exit yet; detect and handle process death below
            _log.critical(f"Broken pipe sending to eye {eye} worker")
        except (OSError, subprocess.SubprocessError):
            raise DisplayError(f"Error sending to eye {eye} worker")

        if worker.returncode is not None:
            # Exit codes 42 (Ctrl-Q) and 1 (Ctrl-R) are user-requested exits.
            # Propagate the exit code (systemctl stops the service on 42).
            if (code := worker.returncode) in (42, 1):
                _log.critical(f"Propagating exit {code} from eye {eye} worker")
                raise SystemExit(code)

            raise DisplayError(f"Eye {eye} worker died: {worker.returncode}")
