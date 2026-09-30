#!/usr/bin/env python3
"""Restore the stock Creality MJPEG stream. Requires Python 3.8 or newer."""

import http.client
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request


CAMERA_SCRIPT = Path("/usr/bin/auto_uvc.sh")
BIN_DIR = Path("/usr/bin")
PLUGIN_DIR = Path("/usr/lib/mjpg-streamer")
DEVICE_DIR = Path("/dev/v4l/by-id")
BACKUP_DIR = Path("/usr/data/helper-script-backup")
USB_SERVICE = Path("/etc/init.d/S50usb_camera")


def enable_streaming(source):
    lines = source.splitlines(keepends=True)
    commands = [re.sub(r"^[ \t]*#?[ \t]*", "", line).rstrip() for line in lines]
    startup = [
        "LD_LIBRARY_PATH=/usr/lib/mjpg-streamer/ \\",
        "start-stop-daemon -S -b -m -p /var/run/$1_mjpg.pid \\",
        '--exec $MJPG_STREAMER -- -i "input_memfd.so -t $MAIN_CAM" \\',
        '-o "output_http.so -w /usr/share/mjpg-streamer/www/ -p $MAIN_PORT"',
    ]
    starts = [i for i in range(len(lines) - 3) if commands[i:i + 4] == startup]
    stops = [i for i, command in enumerate(commands)
             if command == "start-stop-daemon -K -p /var/run/$1_mjpg.pid"]
    # Only restore the known stock commands; leave unfamiliar firmware untouched.
    if len(starts) != 1 or len(stops) != 1:
        raise ValueError("Unrecognized camera startup/shutdown layout; no changes made.")
    for i in list(range(starts[0], starts[0] + 4)) + stops:
        lines[i] = re.sub(r"^([ \t]*)#", r"\1", lines[i], count=1)
    return "".join(lines)


def activate():
    if os.geteuid() != 0:
        raise ValueError("Run this helper as root on the printer.")
    if USB_SERVICE.exists():
        raise ValueError("USB Camera Support is installed. Remove it through the Helper "
                         "Script Remove menu before activating the stock Creality camera.")
    for executable in (CAMERA_SCRIPT, BIN_DIR / "cam_app", BIN_DIR / "mjpg_streamer"):
        if not executable.is_file() or not os.access(str(executable), os.X_OK):
            raise ValueError("Missing stock camera executable: {}".format(executable))
    for plugin in ("input_memfd.so", "output_http.so"):
        if not (PLUGIN_DIR / plugin).is_file():
            raise ValueError("Missing stock camera plugin: {}".format(PLUGIN_DIR / plugin))
    if not any(device.exists() for device in DEVICE_DIR.glob("main-video*")):
        raise ValueError("No Creality main camera detected. Check its connection first.")

    source = CAMERA_SCRIPT.read_text()
    updated = enable_streaming(source)
    ports = re.findall(r"^MAIN_PORT=([0-9]+)[ \t]*$", source, re.MULTILINE)
    if len(ports) != 1 or not 1 <= int(ports[0]) <= 65535:
        raise ValueError("Unrecognized main camera port; no changes made.")
    port = int(ports[0])

    if updated != source:
        # Validate a copy, then replace atomically on the same filesystem.
        with tempfile.TemporaryDirectory(prefix=".activate-camera-",
                                         dir=str(CAMERA_SCRIPT.parent)) as directory:
            candidate = Path(directory) / "auto_uvc.sh"
            shutil.copy2(str(CAMERA_SCRIPT), str(candidate))
            candidate.write_text(updated)
            subprocess.run(["sh", "-n", str(candidate)], check=True, timeout=5)
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="auto_uvc.sh.", suffix=".bak",
                                             dir=str(BACKUP_DIR), delete=False) as backup:
                backup_path = backup.name
            try:
                shutil.copy2(str(CAMERA_SCRIPT), backup_path)
            except OSError:
                os.unlink(backup_path)
                raise
            print("Backup saved: {}".format(backup_path), flush=True)
            os.replace(str(candidate), str(CAMERA_SCRIPT))
    else:
        print("Stock camera streaming is already enabled.", flush=True)

    print("Reloading the Creality camera service...", flush=True)
    subprocess.run(["sh", str(CAMERA_SCRIPT)], env=dict(os.environ, ACTION="reload"),
                   check=True, timeout=30)
    # Bypass proxy settings for the local camera and require an actual JPEG.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    snapshot_url = "http://127.0.0.1:{}/?action=snapshot".format(port)
    for attempt in range(3):
        try:
            with opener.open(snapshot_url, timeout=3) as response:
                if response.status == 200 and response.read(2) == b"\xff\xd8":
                    print("Camera snapshot verified.")
                    print("Stream: http://PRINTER-IP:{}/?action=stream".format(port))
                    print("Firmware updates may require running this helper again.")
                    return
        except (OSError, http.client.HTTPException):
            pass
        if attempt < 2:
            time.sleep(1)
    raise ValueError("Streaming is enabled, but no JPEG snapshot was received on port {}. "
                     "Check the camera service logs and connection.".format(port))


if __name__ == "__main__":
    try:
        activate()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("Error: {}".format(error), file=sys.stderr)
        sys.exit(1)
