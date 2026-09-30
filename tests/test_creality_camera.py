#!/usr/bin/env python3
"""Run with python3 tests/test_creality_camera.py; no printer or network needed."""

import ast
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch
import urllib.error


repo = Path(__file__).resolve().parents[1]
script = repo / "files/scripts/activate_creality_camera.py"
ast.parse(script.read_text(), feature_version=(3, 8))
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("creality_camera", script)
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)

# Commands and comment placement from the reported firmware, at different lines.
source = r'''#!/bin/sh
MAIN_CAM=0
MAIN_PORT=8090
MAIN_PIC_WIDTH=1920
MAIN_PIC_HEIGHT=1080
MAIN_PIC_FPS=10
# Keep this unrelated comment.
start_uvc() {
    case "$1" in
        main-video*)
#            LD_LIBRARY_PATH=/usr/lib/mjpg-streamer/ \
#            start-stop-daemon -S -b -m -p /var/run/$1_mjpg.pid \
#                --exec $MJPG_STREAMER -- -i "input_memfd.so -t $MAIN_CAM" \
#                -o "output_http.so -w /usr/share/mjpg-streamer/www/ -p $MAIN_PORT"
            ;;
        sub-video*)
#            LD_LIBRARY_PATH=/usr/lib/mjpg-streamer/ \
#            start-stop-daemon -S -b -m -p /var/run/$1_mjpg.pid \
#                --exec $MJPG_STREAMER -- -i "input_memfd.so -t $SUB_CAM" \
#                -o "output_http.so -w /usr/share/mjpg-streamer/www/ -p $SUB_PORT"
            ;;
    esac
}
stop_uvc() {
    case "$1" in
        main-video*|sub-video*)
#            start-stop-daemon -K -p /var/run/$1_mjpg.pid
            ;;
    esac
}
'''
expected = source.replace("#            LD_LIBRARY_PATH", "            LD_LIBRARY_PATH", 1)
expected = expected.replace("#            start-stop-daemon -S", "            start-stop-daemon -S", 1)
expected = expected.replace("#                --exec $MJPG_STREAMER", "                --exec $MJPG_STREAMER", 1)
expected = expected.replace("#                -o ", "                -o ", 1)
expected = expected.replace("#            start-stop-daemon -K", "            start-stop-daemon -K")
assert camera.enable_streaming(source) == expected
assert camera.enable_streaming(expected) == expected
indented = source.replace("\n#", "\n  #")
assert camera.enable_streaming(camera.enable_streaming(indented)) == camera.enable_streaming(indented)

with tempfile.TemporaryDirectory(prefix="creality camera ") as directory:
    root = Path(directory)
    camera.CAMERA_SCRIPT = root / "auto_uvc.sh"
    camera.BIN_DIR = root / "bin"
    camera.PLUGIN_DIR = root / "plugins"
    camera.DEVICE_DIR = root / "devices"
    camera.BACKUP_DIR = root / "backups"
    camera.USB_SERVICE = root / "S50usb_camera"
    for folder in (camera.BIN_DIR, camera.PLUGIN_DIR, camera.DEVICE_DIR):
        folder.mkdir()
    for name in ("cam_app", "mjpg_streamer"):
        executable = camera.BIN_DIR / name
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    for name in ("input_memfd.so", "output_http.so"):
        (camera.PLUGIN_DIR / name).touch()
    device = camera.DEVICE_DIR / "main-video-4"
    device.touch()
    reload_log = root / "reload"
    source += '\nprintf "%s" "$ACTION" > "{}"\n'.format(reload_log)
    camera.CAMERA_SCRIPT.write_text(source)
    camera.CAMERA_SCRIPT.chmod(0o751)

    response = MagicMock()
    response.status = 200
    response.read.return_value = b"\xff\xd8"
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    with patch.object(camera.os, "geteuid", return_value=0), \
            patch.object(camera.urllib.request, "build_opener", return_value=opener), \
            patch.object(camera.time, "sleep"), redirect_stdout(io.StringIO()):
        camera.activate()
        assert reload_log.read_text() == "reload"
        backups = list(camera.BACKUP_DIR.iterdir())
        assert len(backups) == 1 and backups[0].read_text() == source
        assert stat.S_IMODE(camera.CAMERA_SCRIPT.stat().st_mode) == 0o751
        enabled = camera.CAMERA_SCRIPT.read_text()
        assert enabled == camera.enable_streaming(source)
        assert opener.open.call_args[0] == ("http://127.0.0.1:8090/?action=snapshot",)
        camera.activate()
        assert camera.CAMERA_SCRIPT.read_text() == enabled
        assert list(camera.BACKUP_DIR.iterdir()) == backups

        def rejected(error_text):
            before = camera.CAMERA_SCRIPT.read_bytes()
            reload_log.unlink(missing_ok=True)
            try:
                camera.activate()
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                assert error_text in str(error), error
            else:
                raise AssertionError("Activation should have failed")
            assert camera.CAMERA_SCRIPT.read_bytes() == before
            assert not reload_log.exists()
            assert list(camera.BACKUP_DIR.iterdir()) == backups

        camera.USB_SERVICE.touch()
        rejected("USB Camera Support")
        camera.USB_SERVICE.unlink()
        device.unlink()
        rejected("No Creality main camera")
        device.touch()
        (camera.PLUGIN_DIR / "input_memfd.so").unlink()
        rejected("Missing stock camera plugin")
        (camera.PLUGIN_DIR / "input_memfd.so").touch()
        for bad in (source.replace("$MAIN_CAM", "$UNKNOWN_CAM"),
                    source.replace("MAIN_PORT=8090", "MAIN_PORT=0")):
            camera.CAMERA_SCRIPT.write_text(bad)
            rejected("Unrecognized")
        camera.CAMERA_SCRIPT.write_text(source + "\nif\n")
        rejected("non-zero exit status")
        camera.CAMERA_SCRIPT.write_text(source)
        with patch.object(camera.shutil, "copy2", side_effect=OSError("Cannot copy")):
            rejected("Cannot copy")
        copy2 = camera.shutil.copy2

        def copy_without_backup(original, destination):
            if Path(destination).parent == camera.BACKUP_DIR:
                raise OSError("Backup unavailable")
            return copy2(original, destination)

        with patch.object(camera.shutil, "copy2", side_effect=copy_without_backup):
            rejected("Backup unavailable")

        camera.CAMERA_SCRIPT.write_text(enabled + "\nexit 1\n")
        try:
            camera.activate()
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError("Reload failure was ignored")
        camera.CAMERA_SCRIPT.write_text(enabled)
        response.read.return_value = b"<h"
        opener.open.reset_mock()
        try:
            camera.activate()
        except ValueError as error:
            assert "no JPEG snapshot" in str(error)
        else:
            raise AssertionError("HTML must not count as a camera frame")
        assert opener.open.call_count == 3
        response.read.return_value = b"\xff\xd8"
        opener.open.side_effect = [urllib.error.URLError("Starting"), opener.open.return_value]
        camera.activate()

# Exercise the menu wrapper with a POSIX shell, including a failing helper.
wrapper = "activate_creality_camera() {" + (repo / "scripts/tools.sh").read_text().split(
    "activate_creality_camera() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
for status in (0, 1):
    result = subprocess.run(["sh", "-c", "set -e\n" + wrapper + """
HS_FILES='/path with spaces/files'
python3() { [ "$1" = "$HS_FILES/scripts/activate_creality_camera.py" ] || exit 9; return """ +
                            str(status) + """; }
ok_msg() { echo success; }
error_msg() { echo failure; }
activate_creality_camera
"""], check=True, text=True, capture_output=True)
    assert result.stdout.strip() == ("success" if status == 0 else "failure")

# The real menu must dispatch the new option and return to the menu afterward.
menu = repo / "scripts/menu/K1/tools_menu_K1.sh"
result = subprocess.run(["sh", "-c", '''
. "$1"
clear() { :; }
tools_menu_ui_k1() { :; }
run() { printf "%s %s\\n" "$1" "$2"; }
tools_menu_k1
''', "sh", str(menu)], input="14\nq\n", capture_output=True, text=True,
                        env=dict(os.environ, TERM="dumb"), check=True)
assert result.stdout.strip() == "activate_creality_camera tools_menu_ui_k1"

print("PASS: activation, backup, repeat runs, preserved settings, safe failures, JPEG check and sh wrapper")
