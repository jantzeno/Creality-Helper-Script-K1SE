#!/usr/bin/env python3
"""Run with python3 tests/test_moonraker_service.py; uses only temporary files."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


repo = Path(__file__).resolve().parents[1]
source = repo / "files/services/S56moonraker_service"
tracked_pids = set()

with tempfile.TemporaryDirectory(prefix="moonraker-service-") as directory:
    root = Path(directory)
    data = root / "data"
    pid_file = root / "moonraker.pid"
    service = root / "service.sh"
    service.write_text(source.read_text().replace(
        "USER_DATA=/usr/data", f"USER_DATA={data}"
    ).replace("PID_FILE=/var/run/moonraker.pid", f"PID_FILE={pid_file}"))
    python = data / "moonraker/moonraker-env/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    script = data / "moonraker/moonraker/moonraker/moonraker.py"
    script.parent.mkdir(parents=True)
    script.write_text('''import json, os, signal, sys
from pathlib import Path
data = Path(sys.argv[2])
if (data / "fail").exists():
    sys.exit(1)
if (data / "ignore-term").exists():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
(data / "state.json").write_text(json.dumps({
    "pid": os.getpid(), "home": os.environ["HOME"],
    "tmpdir": os.environ["TMPDIR"], "args": sys.argv[1:]
}))
while True:
    signal.pause()
''')
    printer_data = data / "printer_data"

    def run(action, succeeds=True):
        result = subprocess.run(["sh", str(service), action], capture_output=True,
                                text=True, timeout=20)
        state = printer_data / "state.json"
        if state.exists():
            tracked_pids.add(json.loads(state.read_text())["pid"])
        assert (result.returncode == 0) == succeeds, (action, result)

    def active_pid():
        pid = int(pid_file.read_text())
        state = json.loads((printer_data / "state.json").read_text())
        assert pid == state["pid"], (pid, state)
        assert state["home"] == "/root"
        assert state["tmpdir"] == str(data / "moonraker/tmp")
        assert state["args"] == ["-d", str(printer_data)]
        return pid

    try:
        subprocess.run(["sh", "-n", str(source)], check=True)
        for stale in ("", "invalid", "-1", "0", "1", "999999999", str(os.getpid())):
            pid_file.write_text(stale)
            run("stop")
            assert not pid_file.exists(), stale

        for stale in ("invalid", "999999999", str(os.getpid())):
            pid_file.write_text(stale)
            run("start")
            pid = active_pid()
            sentinel = data / "moonraker/tmp/keep"
            sentinel.touch()
            run("start")
            assert active_pid() == pid and sentinel.exists()
            run("stop")
            assert not pid_file.exists()

        run("stop")
        run("start")
        for action in ("restart", "reload"):
            previous = active_pid()
            run(action)
            assert active_pid() != previous
        run("stop")
        assert not pid_file.exists()

        (printer_data / "fail").touch()
        run("start", succeeds=False)
        assert not pid_file.exists()
        (printer_data / "fail").unlink()
        python.unlink()
        run("start", succeeds=False)
        assert not pid_file.exists()
        python.symlink_to(sys.executable)

        original = service.read_text()
        service.write_text(original.replace(f"PID_FILE={pid_file}",
                                            f"PID_FILE={root}/missing/moonraker.pid"))
        run("start", succeeds=False)
        service.write_text(original)

        (printer_data / "ignore-term").touch()
        run("start")
        previous = active_pid()
        run("restart", succeeds=False)
        assert active_pid() == previous, "Failed stop must not lose the live PID"
        run("unknown", succeeds=False)
    finally:
        # Only kill children whose command line still identifies this fixture.
        for pid in tracked_pids:
            try:
                if os.fsencode(script) in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"):
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except FileNotFoundError:
                pass

print("PASS: PID identity, stale cleanup, duplicate start, environment, lifecycle and failures")
