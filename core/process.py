"""Helpers for running long-lived subprocesses with live output and cancellation."""

import os
import queue
import re
import signal
import subprocess
import sys
import threading
from typing import Callable, List, Optional, Sequence, Tuple

IS_WINDOWS = sys.platform == "win32"

# Lines kept for error reporting when a subprocess fails
TAIL_LINES = 40


class ProcessCancelled(Exception):
    """Raised when a running operation was cancelled by the user."""


def subprocess_flags() -> dict:
    """Popen keyword arguments that keep child processes out of the way."""
    if IS_WINDOWS:
        # No console window pops up when the GUI was started without one
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    # Own process group so the whole tree can be terminated on cancel
    return {"start_new_session": True}


def kill_process_tree(process: subprocess.Popen) -> None:
    """Terminate a process together with all of its children."""
    if process.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **subprocess_flags(),
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def child_env(extra: Optional[dict] = None) -> dict:
    """Environment for child Python processes: unbuffered UTF-8 output."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # Never let a child inherit the application's own virtual environment
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def run_streaming(
    cmd: Sequence[str],
    *,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    on_line: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Tuple[int, List[str]]:
    """
    Run a command, feeding every output line to ``on_line`` as it appears.

    Carriage returns count as line breaks, so progress bars that redraw a
    single line (tqdm, pip) arrive as individual updates.

    Returns:
        (return code, last lines of output)

    Raises:
        ProcessCancelled: if ``cancel_event`` was set while the command ran
    """
    process = subprocess.Popen(
        [str(part) for part in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=cwd,
        **subprocess_flags(),
    )

    lines: "queue.Queue[Optional[str]]" = queue.Queue()

    def reader():
        try:
            for raw in process.stdout:
                lines.put(raw.rstrip("\n"))
        finally:
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()

    tail: List[str] = []
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise ProcessCancelled()
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                break
            if not line.strip():
                continue
            tail.append(line)
            if len(tail) > TAIL_LINES:
                del tail[0]
            if on_line is not None:
                on_line(line)
        return process.wait(), tail
    except BaseException:
        # Cancelled, interrupted with Ctrl+C or a failing callback: the child
        # runs detached from the terminal, so it has to be stopped explicitly
        kill_process_tree(process)
        raise


_TQDM_PERCENT = re.compile(r"(\d{1,3})%\|")


class BarProgress:
    """
    Turns the output of one or more consecutive tqdm progress bars into a
    single overall percentage.

    Args:
        total_bars: Number of progress bars the process is expected to print
        callback: Called with the overall percentage (0-100)
        accept: Optional filter deciding whether a line belongs to a counted bar
    """

    def __init__(self, total_bars: int, callback: Optional[Callable[[int], None]],
                 accept: Optional[Callable[[str], bool]] = None):
        self.total_bars = max(1, total_bars)
        self.callback = callback
        self.accept = accept
        self.bar_index = 0
        self.last_percent = 0
        self.reported = -1

    def feed(self, line: str) -> bool:
        """Parse an output line. Returns True if it was a progress update."""
        match = _TQDM_PERCENT.search(line)
        if not match:
            return False
        if self.accept is not None and not self.accept(line):
            return True
        percent = min(100, int(match.group(1)))
        if percent < self.last_percent and self.bar_index < self.total_bars - 1:
            # The percentage dropped: a new bar has started
            self.bar_index += 1
        self.last_percent = percent
        overall = int((self.bar_index * 100 + percent) / self.total_bars)
        if overall > self.reported:
            self.reported = overall
            if self.callback is not None:
                self.callback(overall)
        return True
