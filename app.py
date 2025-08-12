#!/usr/bin/env python3
import io
import signal
import threading
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
    """A minimal BufferedIOBase sink for Picamera2's MJPEG encoder."""
    def __init__(self):
        super().__init__()
        self._condition = threading.Condition()
        self._frame = None

    # FileOutput checks for BufferedIOBase; implement the minimal API.
    def writable(self):
        return True

    def write(self, b: bytes):
        # Called by FileOutput for each encoded JPEG frame
        if not isinstance(b, (bytes, bytearray, memoryview)):
            raise TypeError("expected bytes-like object")
        with self._condition:
            self._frame = bytes(b)
            self._condition.notify_all()
        return len(b)

    def get_frame(self):
        with self._condition:
            self._condition.wait_for(lambda: self._frame is not None)
            return self._frame

app = Flask(__name__)

# ---- Camera setup ----
picam2 = Picamera2()

# Adjust for your Pi: RPi 4 is fine at 1280x720@30; RPi 3 may prefer 640x480@30.
VIDEO_SIZE = (1280, 720)
FRAMERATE = 30

config = picam2.create_video_configuration(
    main={"size": VIDEO_SIZE},  # let Picamera2 pick an encoder-friendly format
    controls={"FrameRate": FRAMERATE}
)
picam2.configure(config)

# Optional: continuous AF (silently ignored if unsupported)
try:
    picam2.set_controls({"AfMode": 2})  # 2 = Continuous
except Exception:
    pass

output_sink = StreamingOutput()
encoder = MJPEGEncoder()

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/stream.mjpg")
def stream():
    def gen():
        boundary = b"--frame"
        while True:
            frame = output_sink.get_frame()
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                   frame + b"\r\n")
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

def start_camera():
    picam2.start()
    # IMPORTANT: wrap our BufferedIOBase in FileOutput
    picam2.start_recording(encoder, FileOutput(output_sink))

def stop_camera(*_):
    try:
        picam2.stop_recording()
    except Exception:
        pass
    try:
        picam2.stop()
    except Exception:
        pass

if __name__ == "__main__":
    # Clean shutdown on Ctrl+C or SIGTERM (systemd)
    signal.signal(signal.SIGINT, stop_camera)
    signal.signal(signal.SIGTERM, stop_camera)

    start_camera()
    app.run(host="0.0.0.0", port=8000, threaded=True)
    stop_camera()
