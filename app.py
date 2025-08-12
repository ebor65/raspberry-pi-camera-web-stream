#!/usr/bin/env python3
# Raspberry Pi camera → HTML MJPEG stream (Pi 3/4, 64-bit OS)
# - Uses Picamera2 + Flask
# - Pi-3 friendly defaults to avoid flicker/black frames
import io
import signal
import threading
from flask import Flask, Response, render_template_string

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder, Quality
from picamera2.outputs import FileOutput

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Raspberry Pi Camera</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    html,body{margin:0;padding:0;background:#111;color:#eee;font-family:system-ui,Segoe UI,Roboto,Arial}
    .wrap{display:grid;place-items:center;height:100vh;gap:1rem}
    img{max-width:95vw;max-height:85vh;border-radius:12px;box-shadow:0 0 0 1px #222}
    .bar{opacity:.8}
    code{background:#222;padding:.2em .4em;border-radius:6px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="bar">Live stream at <code>/stream.mjpg</code></div>
    <img src="/stream.mjpg" alt="Live camera stream" />
    <div class="bar">If it struggles on Pi 3, lower resolution or FPS in <code>app.py</code>.</div>
  </div>
</body>
</html>
"""

class StreamingOutput(io.BufferedIOBase):
    """Buffered sink for Picamera2 MJPEG frames; yields each new frame exactly once."""
    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._frame = None
        self._seq = 0

    def writable(self):
        return True

    def write(self, b: bytes):
        if not isinstance(b, (bytes, bytearray, memoryview)):
            raise TypeError("expected bytes-like object")
        with self._cond:
            self._frame = bytes(b)
            self._seq += 1
            self._cond.notify_all()
        return len(b)

    def frames(self):
        """Block until a new frame arrives, then yield it (no duplicates)."""
        last = -1
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._seq != last)
                last = self._seq
                frame = self._frame
            yield frame

app = Flask(__name__)

# ---------- Camera setup (Pi-3 friendly defaults) ----------
# Pi 4 handles 1280x720@25 easily; Pi 3 is happier at 960x540@20 or 640x480@20.
VIDEO_SIZE = (960, 540)  # change to (640, 480) if needed; or (1280, 720) on Pi 4
FRAMERATE = 20           # slightly lower than 30 → smoother on Pi 3
JPEG_QUALITY = Quality.LOW  # use enum, not numbers (avoids KeyError)

picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": VIDEO_SIZE},
    controls={"FrameRate": FRAMERATE}
)
picam2.configure(config)

# Optional autofocus (ignored if sensor doesn't support it)
try:
    picam2.set_controls({"AfMode": 2})  # 2 = Continuous
except Exception:
    pass

output = StreamingOutput()
encoder = MJPEGEncoder()

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/stream.mjpg")
def stream():
    boundary = b"--frame"
    def gen():
        # Only send when a NEW frame arrives (prevents browser buffer stalls/blackouts).
        for frame in output.frames():
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Cache-Control: no-cache, no-store, must-revalidate\r\n"
                   b"Pragma: no-cache\r\n"
                   b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                   frame + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/snapshot.jpg")
def snapshot():
    # Optional: single JPEG endpoint
    frame = next(output.frames())
    return Response(frame, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

@app.route("/healthz")
def health():
    return "ok", 200, {"Cache-Control": "no-cache"}

def start_camera():
    # start_recording starts the camera; no separate picam2.start() needed
    picam2.start_recording(encoder, FileOutput(output), quality=JPEG_QUALITY)

def stop_camera(*_):
    for fn in (picam2.stop_recording, picam2.stop):
        try:
            fn()
        except Exception:
            pass

if __name__ == "__main__":
    # Clean shutdown on Ctrl+C or SIGTERM (e.g., systemd)
    signal.signal(signal.SIGINT, stop_camera)
    signal.signal(signal.SIGTERM, stop_camera)

    start_camera()
    # use_reloader=False to avoid double-starting the camera
    app.run(host="0.0.0.0", port=8000, threaded=True, debug=False, use_reloader=False)
    stop_camera()
