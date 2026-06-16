# Code walkthrough and defense notes

A module-by-module guide to the codebase, the reasoning behind the main design decisions, and
honest answers to the questions most likely to come up. The goal is that you can open any file
and explain what it does and why.

---

## The big picture

`main.py` runs one loop: capture a frame, check for motion, run detection only if something
moved, and turn confirmed detections into an event (snapshot + clip + alert). A Flask web server
runs in a second thread, and when Telegram is enabled a third thread listens for bot commands.
Everything is configured from `config.py`, which is validated before anything starts.

The order of the gates matters: **motion filter → confidence threshold → two-frame confirmation.**
Each one is cheaper than the next, and each one has to pass before the system does anything
expensive or user-facing.

---

## Module by module

### `config.py`
Holds every parameter and a `validate_config()` function that runs at startup. If a value is out
of range or a required file (model, certificate) is missing, it raises and the program refuses
to start with a clear message.
- **Why:** turning silent runtime failures into one clear message at launch.
- **Be ready to explain:** why validate at startup (fail fast), and that Telegram secrets are
  read from environment variables so they're never committed.

### `camera.py`
Captures frames from the IMX708 with Picamera2 at 1280×720, annotates detections, and records
video. It applies a horizontal+vertical flip through a libcamera `Transform`.
- **Why the flip:** the camera is mounted upside-down. Correcting it in software matters for
  accuracy too — the detector was trained on upright people, so an inverted frame scores lower.
- **Be ready to explain:** why orientation affects detection confidence, and that the flip is
  config-driven (`CAMERA_HFLIP`/`CAMERA_VFLIP`).

### `motion.py`
A pixel-difference motion detector. It blurs the frame, compares it to the previous one, and
measures the changed area. If nothing moved, the frame never reaches the model.
- **Why:** running the neural network on every frame would waste CPU on an empty scene. The
  filter is ~5 ms vs ~43 ms for an inference, so it removes most of the work on a still camera.
- **Detail:** the previous-frame buffer resets after 30 s of stillness, so a slow lighting
  change doesn't register as motion.

### `detector.py`
Loads EfficientDet-Lite0 (INT8) with the LiteRT runtime and runs inference. It keeps only
security classes above the confidence threshold (0.40), then applies a confirmation filter: a
label must appear in two consecutive inferences before it's reported.
- **Why a small model:** speed on the Pi's CPU. INT8 quantization makes it faster and smaller.
- **Why the two-frame filter:** a single frame can produce a one-off false positive; requiring
  two in a row removes most of them at the cost of a small delay.
- **Be ready to explain:** the speed-vs-range trade-off — the model is weaker at distance, and
  you deliberately did not lower the threshold (it would add false positives and heat).
  `DETECTION_DEBUG` can log the raw scores; it was used during tuning and is off by default.

### `storage.py`
Saves snapshots (JPEG) and recordings (AVI), manages disk space, and sets up logging.
- **Event timing:** a snapshot and its clip share a timestamp, which the web UI uses to pair a
  clip with its snapshot thumbnail.
- **Disk cleanup:** when usage passes 90%, the oldest files are deleted until it drops below 85%;
  a file currently being recorded is never deleted.
- **Logging:** rotating files (5 MB × 3) so logs can't fill the disk.

### `main.py`
The orchestrator and the main loop. On a confirmed detection with no recording in progress, it
saves one snapshot, sends one alert, and starts recording; recording stops after a cooldown with
no detections.
- **Why event-based:** the earlier design saved an image every few seconds, producing piles of
  near-identical snapshots. One snapshot + one clip per appearance is cleaner and uses less disk.
- **Be ready to explain:** the threading model (main loop, web thread, bot thread) and the
  graceful shutdown (release the camera, finalize the clip).

### `web.py` + `auth.py`
A Flask app served over HTTPS. Every route needs HTTP basic auth. The page gets live updates
through Server-Sent Events, and snapshots open in a zoom/pan viewer.
- **Auth:** credentials are stored as a username and a SHA-256 hash in `auth.txt` (created with
  `0600` permissions); a strong random password is generated on first run. Comparison is
  constant-time.
- **Why SSE and not polling:** the server pushes events the moment they happen, so the page
  updates without reloading and without the client hammering the server.
- **Be ready to explain:** how a detection reaches the browser (loop calls `push_event`, the
  `/stream` endpoint sends it to each connected client through a queue).

### `telegram_notify.py` + `telegram_bot.py`
`telegram_notify.py` sends one-way alerts with a photo, with a global and a per-label cooldown so
one event doesn't flood the chat. `telegram_bot.py` long-polls for commands and answers them, and
only accepts commands from the configured chat ID.
- **Be ready to explain:** the difference between the two (outgoing alerts vs incoming commands),
  and that the token/chat ID come from environment variables.

### `mock_camera.py` + `test_system.py`
`mock_camera.py` is a drop-in replacement for the camera that feeds a still image, so
`test_system.py` can run the entire pipeline without the Pi hardware.
- **Why:** lets you develop and test the web interface and detection logic on any machine.

### `benchmark.py` + `verify_install.py`
`benchmark.py` measures inference, motion, and system performance. `verify_install.py` runs a
36-point check of the environment, files, model, certificate, camera, and service.
- **Be ready to explain:** these are how you produced the performance numbers and how you confirm
  a clean install.

---

## Likely questions, and honest answers

**Why EfficientDet-Lite0 and not something bigger / YOLO?**
It's small and quantized, so it runs fast on the Pi's CPU without an accelerator. A bigger model
or a Coral/Hailo accelerator would detect at longer range but adds cost and complexity. The
project's goal was a complete, self-contained system on plain hardware.

**Why does it miss people far away or in the dark?**
The small model's confidence drops below the threshold for distant or poorly-lit subjects. This
is shown honestly in the report. Lowering the threshold would catch some of them but admit false
positives and raise the sustained CPU and thermal load, so it's left as a known limitation.

**Why a separate motion filter if the model already detects objects?**
Cost. Inference is ~43 ms; the motion check is ~5 ms. On a fixed camera most frames are static,
so the filter avoids running the model on nothing and keeps the Pi cool.

**Why require two consecutive frames?**
To suppress one-frame false positives. A real person stays in view across frames; a spurious
single-frame detection does not.

**How does the live web update work without reloading?**
Server-Sent Events. The detection loop calls `push_event`, and the `/stream` endpoint streams
those events to each connected browser, which updates the page in JavaScript.

**How are passwords handled?**
Stored as a SHA-256 hash, never in plain text; the file is `0600`; comparison is constant-time;
a strong password is required and generated randomly on first run.

**Why AVI and not MP4?**
OpenCV writes AVI directly with no extra dependency. MP4 in the browser would need transcoding;
that's listed as future work.

**Is it secure to expose?**
It's designed for the local network behind a self-signed certificate and basic auth. It is not
meant to be exposed directly to the public internet.

**How do you know it's stable?**
It runs as a systemd service with automatic restart, logs with rotation so they can't fill the
disk, cleans up old files, and shuts down cleanly. The install verifier confirms the setup.
