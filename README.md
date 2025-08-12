# Raspberry Pi Camera Web Stream

A tiny Flask + Picamera2 app that serves your Raspberry Pi camera as an MJPEG stream at `/stream.mjpg` and a simple HTML page at `/`.

## Hardware / OS
- Raspberry Pi 3 or 4
- 64‑bit Raspberry Pi OS (Bullseye or Bookworm)
- Any libcamera‑supported camera module (IMX219/IMX477/IMX708, etc.)

## 1) Install system packages
```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-flask libcamera-apps
