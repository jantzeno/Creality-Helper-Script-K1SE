#!/usr/bin/env python3
"""Run with python3 tests/test_k1_cleanup.py; no printer or network needed."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


repo = Path(__file__).resolve().parents[1]


def shell(command, env, answer=""):
    return subprocess.run(["sh", "-c", command], env=env, input=answer,
                          capture_output=True, text=True, timeout=10)


with tempfile.TemporaryDirectory(prefix="k1 cleanup ") as directory:
    root = Path(directory)
    env = dict(os.environ, TEST_ROOT=str(root), REPO=str(repo))

    # Boot the real helper with hardware discovery and system mutations replaced.
    (root / "scripts").symlink_to(repo / "scripts", target_is_directory=True)
    tools = root / "tools"
    tools.mkdir()
    model_tool = tools / "model"
    model_tool.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_MODEL"\nexit "$MODEL_STATUS"\n')
    model_tool.chmod(0o755)
    stub = tools / "stub"
    stub.write_text('''#!/bin/sh
printf '%s %s\n' "${0##*/}" "$*" >> "$TEST_ROOT/commands"
[ "${0##*/}" != git ] || echo test
''')
    stub.chmod(0o755)
    for name in ("cp", "chmod", "ln", "rm", "git", "clear"):
        (tools / name).symlink_to(stub)
    helper = root / "helper.sh"
    helper.write_text((repo / "helper.sh").read_text().replace(
        "/usr/bin/get_sn_mac.sh", shlex.quote(str(model_tool))))
    startup_env = dict(env, PATH=str(tools) + ":" + env["PATH"])
    for model, status, accepted in (
        ("K1", 0, True), ("K1 Max", 0, True), ("K1C", 0, True),
        ("K1 SE", 0, True), ("k1se", 0, True),
        *((model, 0, False) for model in ("F001", "F002", "F003", "F004", "F005", "unknown", "")),
        ("K1", 1, False),
    ):
        (root / "commands").write_text("")
        answer = "1\nb\n2\nb\n3\nb\n4\nb\n5\nb\n6\nb\nq\n" if model == "K1" else "q\n"
        result = shell('sh "$TEST_ROOT/helper.sh"',
                       dict(startup_env, TEST_MODEL=model, MODEL_STATUS=str(status)), answer)
        assert (result.returncode == 0) == accepted, (model, result)
        if accepted:
            assert "HELPER SCRIPT FOR CREALITY K1 SERIES" in result.stdout, result
            if model == "K1":
                for title in ("INSTALL", "REMOVE", "CUSTOMIZE", "BACKUP & RESTORE", "TOOLS", "INFORMATION"):
                    assert f"[ {title} MENU ]" in result.stdout, result
                for removed in ("Fluidd", "Guppy", "REMOTE ACCESS", "Octo", "Obico", "Mobileraker", "SimplyPrint"):
                    assert removed not in result.stdout, result
        else:
            assert "K1 Series" in result.stderr and not (root / "commands").read_text(), result
    model_tool.unlink()
    (root / "commands").write_text("")
    result = shell('sh "$TEST_ROOT/helper.sh"', startup_env, "q\n")
    assert result.returncode != 0 and not (root / "commands").read_text(), result

    features = (
        ("moonraker_nginx", "MOONRAKER_FOLDER", "Moonraker and Nginx"),
        ("mainsail", "MAINSAIL_FOLDER", "Mainsail (port 4409)"),
        ("entware", "ENTWARE_FILE", "Entware"),
        ("gcode_shell_command", "KLIPPER_SHELL_FILE", "Klipper Gcode Shell Command"),
        ("kamp", "KAMP_FOLDER", "Klipper Adaptive Meshing & Purging"),
        ("buzzer_support", "BUZZER_FILE", "Buzzer Support"),
        ("nozzle_cleaning_fan_control", "NOZZLE_CLEANING_FOLDER", "Nozzle Cleaning Fan Control"),
        ("fans_control_macros", "FAN_CONTROLS_FILE", "Fans Control Macros"),
        ("improved_shapers", "IMP_SHAPERS_FOLDER", "Improved Shapers Calibrations"),
        ("useful_macros", "USEFUL_MACROS_FILE", "Useful Macros"),
        ("save_zoffset_macros", "SAVE_ZOFFSET_FILE", "Save Z-Offset Macros"),
        ("screws_tilt_adjust", "SCREWS_ADJUST_FILE", "Screws Tilt Adjust Support"),
        ("m600_support", "M600_SUPPORT_FILE", "M600 Support"),
        ("git_backup", "GIT_BACKUP_FILE", "Git Backup"),
        ("moonraker_timelapse", "TIMELAPSE_FILE", "Moonraker Timelapse"),
        ("camera_settings_control", "CAMERA_SETTINGS_FILE", "Camera Settings Control"),
        ("usb_camera", "USB_CAMERA_FILE", "USB Camera Support"),
    )
    installed = {}
    for _, variable, _ in features:
        path = root / variable
        path.mkdir() if variable.endswith("_FOLDER") else path.touch()
        installed[variable] = str(path)
    absent = {variable: str(root / (variable + "-absent")) for variable in installed}
    stock = root / "stock-web"
    stock.touch()
    init = root / "init"
    init.mkdir()
    (init / "S99start_app").touch()
    env.update(CREALITY_WEB_FILE=str(stock), INITD_FOLDER=str(init), NGINX_FOLDER=str(root))
    menu_command = '''
. "$REPO/scripts/menu/functions.sh"
. "$REPO/scripts/menu/K1/${MENU}_menu_K1.sh"
clear() { :; }
version_line() { :; }
get_script_version() { echo test; }
v4l2-ctl() { :; }
run() { printf 'ACTION %s\n' "$1"; }
"${MENU}_menu_k1"
'''
    for action in ("install", "remove"):
        for number, (feature, variable, _) in enumerate(features, 1):
            state = dict(installed if action == "install" else absent)
            state[variable] = (absent if action == "install" else installed)[variable]
            result = shell(menu_command, dict(env, **state, MENU=action), f"{number}\nq\n")
            assert result.returncode == 0, result
            assert re.findall(r"^ACTION (.*)$", result.stdout, re.M) == [f"{action}_{feature}"], result
            options = re.findall(r"(\d+)\) (?:Install|Remove) ([^│]+)", result.stdout)
            assert [(int(n), label.strip()) for n, label in options] == [
                (n, label) for n, (_, _, label) in enumerate(features, 1)
            ], result.stdout
        result = shell(menu_command, dict(env, **absent, MENU=action),
                       "18\n19\n20\n21\n22\n23\n24\nq\n")
        assert result.returncode == 0 and "ACTION " not in result.stdout, result
        assert result.stdout.count("Please select a correct choice!") == 7, result

    result = shell(menu_command, dict(env, **installed, MENU="remove",
                                    CREALITY_WEB_FILE=str(root / "absent-stock")), "2\nq\n")
    assert result.returncode == 0 and "ACTION " not in result.stdout, result
    assert "Please restore Creality Web Interface first" in result.stdout, result

    for number, action in enumerate(("install_custom_boot_display", "remove_custom_boot_display",
                                     "remove_creality_web_interface", "restore_creality_web_interface"), 1):
        state = dict(env, **installed, MENU="customize", BOOT_DISPLAY_FOLDER=str(root),
                     BOOT_DISPLAY_FILE=str(stock if number == 2 else root / "absent-boot"))
        if number == 4:
            state["CREALITY_WEB_FILE"] = str(root / "absent-stock")
        result = shell(menu_command, state, f"{number}\nq\n")
        assert result.returncode == 0 and f"ACTION {action}\n" in result.stdout, result
    result = shell(menu_command, dict(env, **installed, MENU="customize"), "5\n6\n7\nq\n")
    assert result.returncode == 0 and "ACTION " not in result.stdout, result
    assert result.stdout.count("Please select a correct choice!") == 3, result

    # Exercise installation into a temporary printer, with no downloads or services.
    nginx = root / "nginx"
    (nginx / "nginx").mkdir(parents=True)
    (nginx / "sbin").mkdir()
    (root / "moonraker/moonraker").mkdir(parents=True)
    validator = nginx / "sbin/nginx"
    validator.write_text('''#!/bin/sh
cmp -s "$NGINX_CONF_URL" "$3" || exit 2
echo VALIDATED
exit "$VALIDATION_STATUS"
''')
    validator.chmod(0o755)
    install_env = dict(env, NGINX_FOLDER=str(nginx), USR_DATA=str(root),
                       MOONRAKER_FOLDER=str(root / "moonraker"),
                       PRINTER_DATA_FOLDER=str(root), KLIPPER_CONFIG_FOLDER=str(root),
                       NGINX_CONF_URL=str(repo / "files/moonraker/nginx.conf"),
                       NGINX_URL="nginx-archive", MOONRAKER_URL1="moonraker-archive",
                       MOONRAKER_URL2=str(repo / "files/moonraker/moonraker.conf"),
                       MOONRAKER_URL3=str(repo / "files/moonraker/moonraker.asvc"),
                       NGINX_SERVICE_URL=str(repo / "files/services/S50nginx"),
                       MOONRAKER_SERVICE_URL=str(repo / "files/services/S56moonraker_service"))
    install_command = '''
. "$REPO/scripts/menu/functions.sh"
. "$REPO/scripts/moonraker_nginx.sh"
tar() { echo 'old archive configuration' > "$NGINX_FOLDER/nginx/nginx.conf"; }
mkdir() { :; }
chmod() { :; }
ln() { :; }
git() { :; }
start_nginx() { echo START_NGINX; }
start_moonraker() { echo START_MOONRAKER; }
install_moonraker_nginx
'''
    for status in (1, 0):
        result = shell(install_command, dict(install_env, VALIDATION_STATUS=str(status)), "y\n")
        assert (result.returncode == 0) == (status == 0), result
        assert "VALIDATED" in result.stdout, result
        if status:
            assert "START_" not in result.stdout and not (init / "S50nginx").exists(), result
        else:
            assert result.stdout.index("VALIDATED") < result.stdout.index("START_NGINX"), result
            assert "START_MOONRAKER" in result.stdout and (init / "S50nginx").exists(), result

print("PASS: K1 startup, rejection before changes, menu actions, removal guard and Nginx installation")
