# Creality Helper Script

## About

This script intended for use on Creality **K1 Series** and **Ender-3 V3 Series** printers allows to add more features.

If you don't know what you're doing, I don't recommend following this guide.

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
`http://PRINTER-IP:8080/?action=snapshot` in Fluidd/Mainsail, replacing
`PRINTER-IP` with the printer's address. The helper reports the port configured
in the firmware. Firmware updates may require activating the camera again.

## Default Web Interface

Select **Customize → Remove Creality Web Interface** to put Fluidd or Mainsail
on port 80. If both are installed, choose the interface when prompted. Its
existing port (`4408` for Fluidd or `4409` for Mainsail) remains available.
This disables Creality Print Wi-Fi printing; **Restore Creality Web Interface**
reverses the change.

The helper validates Nginx configuration and checks the selected page over
HTTP before reporting success. Failed changes trigger recovery of the previous
configuration and stock service state. Backups and diagnostics are saved under
`/usr/data/helper-script-backup/web-interface/`. Unrecognized listener layouts
are rejected without changing the live configuration.

If the old interface still appears at `http://PRINTER-IP/`, try a private
browser window, then clear cached files/site data for the printer's IP.

Run the regression check locally with `python3 tests/test_creality_web_interface.py`.
It uses temporary files and simulated services; no printer or network is needed.

## Wiki

Guide to use it is available here: [Wiki](https://guilouz.github.io/Creality-Helper-Script-Wiki/)

<br />
