# Presentation — slide content and demo flow

Source for the defense slide deck (10–15 minutes + Q&A). Each section below is one slide:
the heading is the slide title, the bullets are what goes on the slide (keep them short on the
actual slide), and **Say:** is what you talk through out loud. Aim for ~8 minutes of slides and
~5 minutes of live demo, leaving room for questions.

---

## Slide 1 — Title

- Intelligent Edge-AI Security Camera
- Nikoloz Oniani — Caucasus University, 2026
- Real-time person and vehicle detection on a Raspberry Pi 5

**Say:** One line — "A security camera that detects people and vehicles in real time and runs
entirely on a Raspberry Pi, with no cloud service."

## Slide 2 — The problem

- Consumer cameras depend on the cloud
- Footage leaves your network; features sit behind subscriptions
- You don't control where the video goes

**Say:** Frame the gap: the common product sends everything to a vendor's servers. The goal was
to do the same core job — detect and alert — without any of that.

## Slide 3 — Goal

- Detect people and vehicles in a live feed, in real time
- Do all processing on the device — no cloud
- Record events and notify the user
- Be stable enough to run unattended

**Say:** These four points are the success criteria; the rest of the talk shows each one is met.

## Slide 4 — System overview

- Single Raspberry Pi 5 with a camera
- One Python application + a background web server
- *(architecture diagram from the technical report)*

**Say:** Walk the architecture diagram left to right: camera → motion filter → detector →
storage/notify, with the web dashboard and Telegram on the side.

## Slide 5 — Hardware

- Raspberry Pi 5 (8 GB)
- Arducam IMX708 wide-angle camera
- 64 GB microSD, 27 W (5 V/5 A) power
- Raspberry Pi OS 64-bit

**Say:** Mention the power point honestly — an undersized supply caused under-voltage
shutdowns early on; the 5 V/5 A supply fixed it. It shows you debugged a real hardware issue.

## Slide 6 — How it works (the pipeline)

- Capture a frame
- Motion filter — skip still scenes before any AI
- Detection — run the model only on moving frames
- Confirm — require the object in two consecutive frames
- Event — save one snapshot, record a clip, alert
- *(detection-pipeline flow diagram)*

**Say:** Emphasize the gates: motion first (cheap), then the model, then a confirmation check.
Each gate means you only spend CPU and only fire an alert when it's worth it.

## Slide 7 — Detection

- EfficientDet-Lite0, INT8 quantized, via TensorFlow Lite (LiteRT)
- Classes: person, car, motorcycle, bus, truck, bicycle
- Small model chosen for speed on the Pi's CPU
- Motion pre-filter + two-frame confirmation reduce false positives

**Say:** Explain the trade-off you made on purpose: a small model is fast but weaker at range;
you kept the threshold where it is rather than chasing distant detections, because lowering it
adds false positives and heat. That's a deliberate engineering decision, not a gap.

## Slide 8 — Features

- Web dashboard over HTTPS, live updates (Server-Sent Events)
- Snapshot viewer: click to enlarge, scroll to zoom, drag to pan
- Event-based capture: one snapshot + one clip per appearance
- Telegram: photo alerts + interactive bot (`/status`, `/snapshot`, `/stop`, ...)
- Basic auth, automatic disk cleanup, runs as a systemd service

**Say:** Keep this quick — you'll show most of it in the demo. Call out event-based capture as a
design improvement over saving an image every few seconds.

## Slide 9 — Performance

| Metric | Result |
|---|---|
| Inference | 42.7 ms (23.4 FPS) |
| Motion filter | 5.3 ms (~190 FPS) |
| CPU temp under load | 58.7 °C |
| RAM | 588 MB / 8 GB |

**Say:** The capture loop runs at 10 FPS, so 23 FPS of inference is ~2.3× headroom. The motion
filter is ~8× cheaper than an inference, so a still scene costs almost nothing. The Pi stays
well under its ~80 °C throttle point. These are measured with the `benchmark.py` script.

## Slide 10 — Engineering practices

- Startup configuration validation
- 36-point install verifier (`verify_install.py`)
- Hardware-free testing with a mock camera
- Version control: feature branches and pull requests
- Secrets (Telegram token) kept out of the repository via environment variables

**Say:** This slide answers "is it a real, maintainable project." Mention you can run the
verifier live if asked.

## Slide 11 — Limitations and future work

- Small model: weaker on distant or poorly-lit subjects
- Recordings are AVI (download, not in-browser playback)
- Single camera, designed for the local network

**Say:** Being honest about limits reads as maturity. Each has a clear next step: a bigger model
or an accelerator, MP4 transcoding, multi-camera support.

## Slide 12 — Live demo

*(No bullets — switch to the running system.)*

**Demo script (have the dashboard open and the service running):**
1. Show the dashboard — status bar (counts, disk), the layout.
2. Walk into the camera's view. Point out, live: the detection toast, a new snapshot appearing,
   a new recording card, and the Telegram alert arriving on your phone.
3. Click a snapshot — scroll to zoom, drag to pan.
4. In Telegram, send `/status` and `/snapshot` — show the replies.
5. (Optional) `/stop` then `/start` to show remote control.
6. Mention it auto-starts on boot via systemd.

**Backup:** if the live demo fails, have a short screen recording of the same steps ready.

## Slide 13 — Conclusion

- A complete, on-device security camera: real-time detection, recording, web + Telegram
- Runs in real time and stays cool enough for continuous use
- Fully local — no cloud, no subscription

**Say:** Close by restating the four goals from Slide 3 and that each is met.

## Slide 14 — Thank you / Q&A

- Repository: github.com/onianinikoloz1643-blip/security-camera-pi
- Questions

**Say:** Keep the repo and the architecture diagram on screen during questions.

---

### Timing

| Section | Time |
|---|---|
| Slides 1–11 | ~7–8 min |
| Live demo (slide 12) | ~4–5 min |
| Q&A | remaining |

### Before you present

- Service running and the dashboard open in a browser tab.
- Telegram open on your phone, bot enabled.
- Good lighting and a clear approach to the camera (detection is best at close-to-medium range).
- Backup screen recording ready.
