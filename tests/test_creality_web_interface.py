#!/usr/bin/env python3
"""Run with python3 tests/test_creality_web_interface.py; no printer or network."""

import json
import os
from pathlib import Path
import subprocess
import tempfile


repo = Path(__file__).resolve().parents[1]
source = repo / "scripts/creality_web_interface.sh"
template = (repo / "files/moonraker/nginx.conf").read_text()
subprocess.run(["sh", "-n", str(source)], check=True)

# Stand-ins model the running configuration separately from the file on disk.
# They never signal printer processes or make network requests.
stub = r'''#!/usr/bin/env python3
import json, os, re, signal, sys, time
from pathlib import Path

root = Path(os.environ["WEB_TEST_ROOT"])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
state = json.loads((root / "state.json").read_text())
fault = (root / "fault").read_text() if (root / "fault").exists() else ""

def save():
    path = root / ("state." + str(os.getpid()))
    path.write_text(json.dumps(state))
    path.replace(root / "state.json")

with (root / "commands").open("a") as log:
    log.write(name + " " + " ".join(args) + "\n")

if name == "sleep":
    time.sleep(0.02)
elif name == "mv":
    fail_move = (fault == "move" and Path(args[0]).name == "web-server"
                 or fault == "apply" and Path(args[0]).name.startswith("nginx.conf."))
    if fail_move and not state.get("move_failed"):
        state["move_failed"] = True
        save()
        sys.exit(1)
    os.replace(*args)
elif name == "pidof":
    if args[0] not in state["running"]:
        sys.exit(1)
    print(1234)
elif name == "killall":
    if fault == "stop" and not state.get("stop_failed"):
        state["stop_failed"] = True
        save()
        sys.exit(1)
    state["running"] = [p for p in state["running"] if p != args[-1]]
    save()
elif name in ("web-server", "Monitor"):
    if fault == "stock_start" and name == "web-server":
        sys.exit(1)
    # Refuse a competing listener, just like the real stock web server.
    if name == "web-server" and state["nginx_port"]:
        sys.exit(1)
    state["running"].append(name)
    save()
elif name == "nginx":
    config = Path(args[args.index("-c") + 1])
    text = config.read_text()
    if "-t" in args:
        if fault == "validation" or "INVALID" in text:
            print("nginx: simulated validation error", file=sys.stderr)
            sys.exit(1)
    else:
        assert args[-2:] == ["-s", "reload"], args
        state["reloads"] += 1
        if fault == "recovery" or (fault == "reload" and state["reloads"] == 1):
            save()
            print("nginx: simulated reload error", file=sys.stderr)
            sys.exit(1)
        owner = re.search(r"listen\s+(4409)\s+default_server;\s+listen 80;", text)
        state["nginx_port"] = int(owner[1]) if owner else 0
        state["active_config"] = text
        save()
        if fault == "signal" and state["reloads"] == 1:
            os.kill(os.getppid(), signal.SIGTERM)
elif name == "curl":
    assert args[0] == "-q"
    assert args[args.index("--noproxy") + 1] == "*"
    assert args[args.index("--max-time") + 1] == "2"
    port = int(re.search(r":(\d+)/$", args[-1])[1])
    output = args[args.index("--output") + 1]
    actual = port
    if port == 80:
        actual = state["nginx_port"]
        if not actual and "web-server" in state["running"]:
            actual = "creality"
    status = 200
    if actual == 4409:
        page = root / "mainsail/index.html"
        body = page.read_text() if page.exists() else ""
        if not body:
            status = 404
    elif actual == "creality":
        body = "<html>Creality</html>"
    else:
        if "--write-out" in args:
            print("000", end="")
        print("curl: connection refused", file=sys.stderr)
        sys.exit(7)
    if port == 80 and state["reloads"] == 1:
        if fault == "wrong_page":
            body = "<html>Wrong interface</html>"
        elif fault == "http_error":
            status = 503
        elif fault == "retry" and state.get("retries", 0) < 2:
            state["retries"] = state.get("retries", 0) + 1
            save()
            sys.exit(7)
    if "--write-out" in args:
        print(status, end="")
    if output != "/dev/null":
        Path(output).write_text(body)
    sys.exit(22 if status >= 400 else 0)
else:
    raise AssertionError(name)
'''

with tempfile.TemporaryDirectory(prefix="web interface ") as directory:
    root = Path(directory)
    tools = root / "tools"
    services = root / "stock"
    tools.mkdir()
    services.mkdir()
    tool = tools / "stub"
    tool.write_text(stub)
    tool.chmod(0o755)
    for name in ("nginx", "curl", "pidof", "killall", "sleep", "mv"):
        (tools / name).symlink_to(tool)
    (root / "mainsail").mkdir()
    (root / "mainsail/index.html").write_text("<html>mainsail</html>")
    (root / "init").mkdir()
    (root / "init/S99start_app").touch()
    (root / "nginx/sbin").mkdir(parents=True)
    (root / "nginx/sbin/nginx").symlink_to(tool)
    script = source
    env = dict(os.environ, WEB_TEST_ROOT=str(root), PATH=str(tools) + ":" + os.environ["PATH"],
               CURL=str(tools / "curl"), NGINX_FOLDER=str(root / "nginx"),
               CREALITY_WEB_FILE=str(services / "web-server"),
               MAINSAIL_FOLDER=str(root / "mainsail"),
               HS_BACKUP_FOLDER=str(root / "backups"), INITD_FOLDER=str(root / "init"))

    def setup(owner=0, monitor=True):
        config = root / "nginx/nginx/nginx.conf"
        config.parent.mkdir(parents=True, exist_ok=True)
        text = template
        if owner:
            text = text.replace(f"listen {owner} default_server;",
                                f"listen {owner} default_server;\n        listen 80;")
        config.write_text(text)
        config.chmod(0o640)
        for name in ("web-server", "Monitor"):
            for suffix in ("", ".disabled"):
                (services / (name + suffix)).unlink(missing_ok=True)
            enabled = not owner and (name == "web-server" or monitor)
            (services / (name + ("" if enabled else ".disabled"))).symlink_to(tool)
        running = [] if owner else ["web-server"] + (["Monitor"] if monitor else [])
        (root / "state.json").write_text(json.dumps({
            "nginx_port": owner, "running": running, "reloads": 0, "active_config": text,
        }))
        (root / "fault").unlink(missing_ok=True)
        (root / "commands").write_text("")
        return config

    def state():
        return json.loads((root / "state.json").read_text())

    def snapshot(config):
        return (config.read_bytes(), config.stat().st_mode,
                sorted(p.name for p in services.iterdir()), sorted(state()["running"]),
                state()["nginx_port"])

    def run(target="mainsail", success=True, action="result", answer=""):
        command = '''
. "$1"
top_line() { :; }
title() { :; }
inner_line() { :; }
hr() { :; }
bottom_line() { :; }
ok_msg() { printf 'OK: %s\\n' "$1"; }
error_msg() { printf 'ERROR: %s\\n' "$1"; }
check_ipaddress() { echo 192.0.2.1; }
remove_msg() { read -r "$2"; }
restore_msg() { read -r "$2"; }
case "$3" in
    result) web_interface_result "$2";;
    remove) remove_creality_web_interface;;
    restore) restore_creality_web_interface;;
esac
echo MENU_ALIVE
'''
        result = subprocess.run(["sh", "-c", command, "sh", str(script), target, action],
                                env=env, input=answer, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0 and "MENU_ALIVE" in result.stdout, result
        if success is not None:
            assert ("OK:" in result.stdout) == success, result
            assert ("ERROR:" in result.stdout) != success, result
        return result

    # Repeated Mainsail switching and stock restoration are idempotent.
    config = setup()
    original = snapshot(config)
    result = run()
    assert state()["nginx_port"] == 4409 and not state()["running"]
    assert config.read_text().count("listen 80;") == 1
    assert config.stat().st_mode == original[1]
    assert "http://192.0.2.1:4409/" in result.stdout
    assert "private window" in result.stdout and "site data" in result.stdout
    switched = snapshot(config)
    run()
    assert snapshot(config) == switched
    run("creality")
    assert snapshot(config) == original
    run("creality")
    assert snapshot(config) == original

    # Preflight failure must not stop stock processes or reload Nginx.
    for fault in ("validation", "missing_marker", "ambiguous", "duplicate", "missing_index",
                  "backup", "conflict", "legacy", "addressed_legacy", "duplicate_mainsail"):
        config = setup()
        if fault == "missing_marker":
            config.write_text(template.replace("listen 4409 default_server;", "listen 9999;"))
        elif fault == "ambiguous":
            config.write_text(template.replace("listen 4409 default_server;", "listen 80;\nlisten 4409 default_server;"))
        elif fault == "duplicate":
            config.write_text(template.replace("listen 4409 default_server;",
                                              "listen 4409 default_server;\nlisten 80;\nlisten 80;"))
        elif fault in ("legacy", "addressed_legacy", "duplicate_mainsail"):
            listener = {"legacy": "4408 default_server", "addressed_legacy": "127.0.0.1:4408",
                        "duplicate_mainsail": "4409 default_server"}[fault]
            config.write_text(template.replace("    server {", "    server {\n        listen " + listener + ";", 1))
        elif fault == "missing_index":
            (root / "mainsail/index.html").rename(root / "saved-index")
        elif fault == "backup":
            (root / "not-a-directory").touch()
            env["HS_BACKUP_FOLDER"] = str(root / "not-a-directory")
        elif fault == "conflict":
            (services / "web-server.disabled").symlink_to(tool)
        else:
            (root / "fault").write_text(fault)
        before = snapshot(config)
        result = run(success=False)
        assert snapshot(config) == before and state()["reloads"] == 0, fault
        if fault in ("legacy", "addressed_legacy"):
            assert "README upgrade steps" in result.stderr, result
        assert "killall" not in (root / "commands").read_text(), fault
        if fault == "missing_index":
            (root / "saved-index").rename(root / "mainsail/index.html")
        env["HS_BACKUP_FOLDER"] = str(root / "backups")

    for fault in ("reload", "wrong_page", "http_error", "stop", "signal", "move", "apply"):
        config = setup(monitor=fault in ("move", "apply"))
        before = snapshot(config)
        (root / "fault").write_text(fault)
        result = run(success=False)
        assert snapshot(config) == before, (fault, result, snapshot(config), before)
        assert "state restored" in result.stderr, result
        assert state()["active_config"] == config.read_text()
        if fault == "wrong_page":
            assert any(p.read_text() == "<html>Wrong interface</html>" for p in
                       (root / "backups").glob("web-interface/*/failed-response"))

    config = setup()
    (root / "fault").write_text("retry")
    run()
    assert state()["retries"] == 2 and state()["reloads"] == 1

    config = setup(owner=4409)
    before = snapshot(config)
    (root / "fault").write_text("stock_start")
    result = run("creality", success=False)
    assert snapshot(config) == before and "state restored" in result.stderr, result

    config = setup()
    (root / "fault").write_text("recovery")
    result = run(success=False)
    assert "Automatic recovery failed" in result.stderr, result
    backups = list((root / "backups/web-interface").iterdir())
    assert any((p / "nginx.log").exists() and (p / "services").exists() for p in backups)
    assert not list(config.parent.glob("nginx.conf.*")), "Candidate files must be cleaned up"

    for action in ("remove", "restore"):
        config = setup()
        before = snapshot(config)
        run(action=action, answer="n\n", success=False)
        assert snapshot(config) == before and not (root / "commands").read_text()
    setup()
    run(action="remove", answer="y\n")
    assert state()["nginx_port"] == 4409
    run(action="restore", answer="y\n")

    config = setup()
    before = snapshot(config)
    (root / "mainsail").rename(root / "absent")
    result = run(action="remove", answer="y\n", success=False)
    assert "Install Mainsail first" in result.stdout
    assert snapshot(config) == before and not (root / "commands").read_text()
    (root / "absent").rename(root / "mainsail")

    config = setup(owner=4409)
    before = snapshot(config)
    (root / "init/S99start_app").unlink()
    run(action="restore", answer="y\n", success=False)
    assert snapshot(config) == before and not (root / "commands").read_text()

    config = setup()
    before = snapshot(config)
    run("fluidd", success=False)
    assert snapshot(config) == before and not (root / "commands").read_text()

print("PASS: Mainsail/stock switching, legacy rejection, HTTP identity, rollback, signals and menus")
