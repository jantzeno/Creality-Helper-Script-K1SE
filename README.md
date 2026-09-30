# Creality Helper Script

## About

This helper adds features to Creality **K1 Series** printers: K1, K1 Max, K1C,
and K1 SE. Other models and failed model detection are rejected before system
changes. Mainsail is the supported alternative web interface.

If you don't know what you're doing, I don't recommend following this guide.

## Upgrade from the full helper

This fork removes support for non-K1 printers, Fluidd and its dynamic logos,
Guppy Screen, OctoEverywhere, Obico, GuppyFLO, SimplyPrint, OctoApp, and Mobileraker.
Updating the repository does not uninstall existing software or migrate live
printer configurations. The removed features have no uninstallers in this fork.

Before updating, use the previous helper to uninstall Guppy Screen and the six
remote integrations, restore the Creality Web Interface, and uninstall Fluidd
(including its dynamic logos). Keep Mainsail and your other K1 features.

Existing Nginx installations require the clean configuration below. Old layouts
containing port 4408 are rejected by web-interface switching. Back up any custom
proxy or camera settings before replacing the configuration; the clean template
restores the helper defaults. Run this as root from the updated repository,
after restoring the stock web interface:

```sh
(
  set -e
  nginx=/usr/data/nginx/sbin/nginx
  config=/usr/data/nginx/nginx/nginx.conf
  backup_dir=$(mktemp -d /usr/data/nginx-config-backup.XXXXXX)
  cp -p "$config" "$backup_dir/nginx.conf"
  echo "Nginx backup: $backup_dir/nginx.conf"
  if cp files/moonraker/nginx.conf "$config" &&
     "$nginx" -t -c "$config" && "$nginx" -c "$config" -s reload; then
    echo "Clean Mainsail configuration installed."
  else
    cp -p "$backup_dir/nginx.conf" "$config"
    if ! "$nginx" -t -c "$config" || ! "$nginx" -c "$config" -s reload; then
      echo "Recovery failed; keep the backup at $backup_dir/nginx.conf." >&2
      exit 1
    fi
    echo "Replacement failed; previous configuration restored." >&2
    exit 1
  fi
)
```

Fresh installations copy and validate this template automatically. Install and
Remove now have choices **1–17**: Moonraker/Nginx is **1**, Mainsail is **2**, and
USB Camera Support is **17**. Customize has choices **1–4**; Tools numbers are
unchanged. There is no automatic removal or migration on startup.

## Activate Creality Camera

On K1 Series printers, including K1 SE, select **Tools → 14: Activate Creality
Camera** to restore the stock MJPEG stream when firmware has commented out its
startup commands. Requires Python 3.8+ and BusyBox-compatible `sh`; no Bash or
additional packages are needed.

The helper checks for the stock camera and plugins, backs up changed scripts
under `/usr/data/helper-script-backup/`, validates the replacement, reloads the
camera service, and verifies a JPEG snapshot. Camera resolution and frame rate
are preserved. If USB Camera Support is installed, remove it first through the
Helper Script Remove menu because it uses a separate streamer.

It can also be run as root from the repository directory:

```sh
python3 files/scripts/activate_creality_camera.py
```

Configure `http://PRINTER-IP:8080/?action=stream` and
`http://PRINTER-IP:8080/?action=snapshot` in Mainsail, replacing
`PRINTER-IP` with the printer's address. The helper reports the port configured
in the firmware. Firmware updates may require activating the camera again.

## Default Web Interface

Select **Customize → 3: Remove Creality Web Interface** to put Mainsail on
port 80. Mainsail also remains available on port **4409**. This disables Creality
Print Wi-Fi printing; **Customize → 4: Restore Creality Web Interface** reverses
the change. Restore the stock interface before removing Mainsail.

The helper validates Nginx configuration and checks the selected page over
HTTP before reporting success. Failed changes trigger recovery of the previous
configuration and stock service state. Backups and diagnostics are saved under
`/usr/data/helper-script-backup/web-interface/`. Unrecognized listener layouts
are rejected without changing the live configuration.

If the old interface still appears at `http://PRINTER-IP/`, try a private
browser window, then clear cached files/site data for the printer's IP.

## Local checks

These checks use temporary files and simulated services; no printer or network
is needed:

```sh
python3 tests/test_k1_cleanup.py
python3 tests/test_creality_web_interface.py
python3 tests/test_creality_camera.py
python3 tests/test_moonraker_service.py
```

## Wiki

The upstream [Wiki](https://guilouz.github.io/Creality-Helper-Script-Wiki/) also
describes features removed from this fork; use the menu numbers in this README.

<br />
