#!/usr/bin/env python3
import io
import signal
import threading
import time
from flask import Flask, Response, render_template_string

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
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
    img{max-width:95vw;max-height:85vh;border-radius:12px}
    .bar{opacity:.8}
    code{background:#222;padding:.2em .4em;border-radius:6px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="bar">Live stream: <code>/stream.mjpg</code></div>
    <img src="/stream.mjpg" alt="Live camera stream" />
    <div class="bar">If you see nothing, try lowering resolution in <code>app.py</code>.</div>
  </div>
</body>
</html>
"""

class StreamingOutput(io.BufferedIOBase):
    """Buffered sink for Picamera2 MJPEG frames with a 'wait-for-new' iterator."""
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
        """Yield each new frame exactly once."""
        last = -1
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._seq != last)
                last = self._seq
                frame = self._frame
            yield frame

app = Flask(__name__)

# ---- Camera setup ----
picam2 = Picamera2()

# Tune for your board; Pi 3 prefers smaller frames. Start conservative if unstable.
VIDEO_SIZE = (1280, 720)  # try (960, 540) or (640, 480) on Pi 3
FRAMERATE = 25            # 25 is gentler than 30 on Pi 3
JPEG_QUALITY = 80         # lower = smaller bandwidth

config = picam2.create_video_configuration(
    main={"size": VIDEO_SIZE},
    controls={"FrameRate": FRAMERATE}
)
picam2.configure(config)

# Optional autofocus (ignored if not supported)
try:
    picam2.set_controls({"AfMode": 2})  # continuous AF
except Exception:
    pass

output = StreamingOutput()
encoder = MJPEGEncoder()  # hardware MJPEG

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/stream.mjpg")
def stream():
    boundary = b"--frame"
    def gen():
        # Stream only when a NEW frame arrives; don't spam duplicates.
        for frame in output.frames():
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                   frame + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

def start_camera():
    # start_recording starts the camera; a separate picam2.start() is not needed.
    picam2.start_recording(encoder, FileOutput(output), quality=JPEG_QUALITY)

def stop_camera(*_):
    for fn in (picam2.stop_recording, picam2.stop):
        try:
            fn()
        except Exception:
            pass

if __name__ == "__main__":
    # Clean shutdown on Ctrl+C or SIGTERM (systemd)
    signal.signal(signal.SIGINT, stop_camera)
    signal.signal(signal.SIGTERM, stop_camera)

    start_camera()
    # Disable the Flask reloader to avoid double-starts of the camera.
    app.run(host="0.0.0.0", port=8000, threaded=True, debug=False, use_reloader=False)
    stop_camera()
