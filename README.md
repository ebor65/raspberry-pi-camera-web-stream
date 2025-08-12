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

sudo raspi-config   # Interface Options → Camera → Enable, then reboot

# pick a location you like
cd ~
git clone https://github.com/<your-user>/raspberry-pi-camera-web-stream.git
cd raspberry-pi-camera-web-stream

# (optional) install Python deps via pip instead of apt for Flask
# python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

python3 app.py

run as a service
sudo cp systemd/raspberry-cam.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-cam.service

