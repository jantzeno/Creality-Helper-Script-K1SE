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

## Wiki

Guide to use it is available here: [Wiki](https://guilouz.github.io/Creality-Helper-Script-Wiki/)

<br />
