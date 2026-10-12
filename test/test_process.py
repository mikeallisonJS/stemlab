import sys
import threading
import time

import pytest

from core.process import BarProgress, ProcessCancelled, run_streaming


def test_run_streaming_returns_lines_and_exit_code():
    lines = []
    code, tail = run_streaming(
        [sys.executable, "-c", "print('one'); print('two'); raise SystemExit(3)"],
        on_line=lines.append,
    )
    assert code == 3
    assert lines == ["one", "two"]
    assert tail == ["one", "two"]


def test_run_streaming_splits_carriage_returns():
    """Progress bars redraw one line with a carriage return; each redraw must arrive separately."""
    lines = []
    script = "import sys; sys.stdout.write('10%|#' + chr(13) + '50%|##' + chr(13) + '100%|###' + chr(10))"
    code, _ = run_streaming([sys.executable, "-c", script], on_line=lines.append)
    assert code == 0
    assert lines == ["10%|#", "50%|##", "100%|###"]


def test_run_streaming_merges_stderr():
    lines = []
    run_streaming([sys.executable, "-c", "import sys; sys.stderr.write('oops' + chr(10))"],
                  on_line=lines.append)
    assert lines == ["oops"]


def test_run_streaming_cancel_kills_process():
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    started = time.time()
    with pytest.raises(ProcessCancelled):
        run_streaming([sys.executable, "-c", "import time; time.sleep(60)"], cancel_event=cancel)
    assert time.time() - started < 20


def test_bar_progress_single_bar():
    seen = []
    bars = BarProgress(1, seen.append)
    for line in ["  0%|          | 0/10", " 50%|#####     | 5/10", "100%|##########| 10/10"]:
        assert bars.feed(line)
    assert seen == [0, 50, 100]
    assert not bars.feed("no progress here")


def test_bar_progress_combines_consecutive_bars():
    seen = []
    bars = BarProgress(4, seen.append)
    for _ in range(4):
        for percent in (0, 50, 100):
            bars.feed(f"{percent:3d}%|###| x")
    assert seen[-1] == 100
    assert seen == sorted(seen), "progress must never go backwards"
    assert 25 in seen and 50 in seen and 75 in seen


def test_bar_progress_ignores_filtered_bars():
    seen = []
    bars = BarProgress(1, seen.append, accept=lambda line: "seconds/s" in line)
    assert bars.feed("100%|###| 80.2M/80.2M [00:01<00:00, 60MB/s]")
    assert seen == []
    bars.feed(" 40%|###| 4/10 [00:01<00:02, 3.0seconds/s]")
    assert seen == [40]


def test_bar_progress_extra_bars_do_not_reset():
    """More bars than expected must not make the progress jump back."""
    seen = []
    bars = BarProgress(1, seen.append)
    for percent in (0, 100, 0, 50, 100):
        bars.feed(f"{percent}%|#|")
    assert seen == sorted(seen)
    assert max(seen) == 100


def test_run_streaming_stops_the_process_when_a_callback_fails(tmp_path):
    """The child runs detached, so nothing else would stop it."""
    marker = tmp_path / "still-running.txt"
    script = (
        "import sys, time; print('started', flush=True); time.sleep(3); "
        f"open({str(marker)!r}, 'w').close()"
    )

    def fail(line):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        run_streaming([sys.executable, "-c", script], on_line=fail)
    time.sleep(4)
    assert not marker.exists(), "the process kept running after the failure"
