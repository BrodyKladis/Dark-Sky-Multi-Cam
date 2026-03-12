import cv2
import time
import threading
import subprocess
import os
import numpy as np
from pygrabber.dshow_graph import FilterGraph

# ================= SETTINGS =================
WIDTH = 1280
HEIGHT = 720
TARGET_FPS = 30  # Desired camera capture FPS (best-effort; depends on camera/driver).

# Long-exposure options:
# - Set LONG_EXPOSURE_SECONDS to a value like 0.5, 1, 2, 5 to enable.
# - "software": accumulates multiple captured frames into one output frame (reliable effect).
# - "hardware": tries to run the camera at low FPS + longer shutter (true sensor exposure if supported).
LONG_EXPOSURE_SECONDS = None
LONG_EXPOSURE_MODE = "hardware"  # "software" or "hardware"
SOFTWARE_BLEND = "mean"  # "mean" (motion blur) or "max" (light trails-ish)

# Post-processing (applied to preview + recorded frames)
# Contrast: 1.0 = unchanged, >1 increases contrast, between 0-1 decreases.
POST_CONTRAST = 10.0

OUTPUT_FPS = (
    (1.0 / float(LONG_EXPOSURE_SECONDS))
    if LONG_EXPOSURE_SECONDS and LONG_EXPOSURE_SECONDS > 0
    else float(TARGET_FPS)
)
FRAME_INTERVAL = 1.0 / OUTPUT_FPS
BITRATE = "5M"
FFMPEG_CODEC = "h264_nvenc"

# Camera exposure/brightness control (best-effort; support varies by camera/driver on Windows).
# If values don't apply, the script will print the resulting cap.get(...) values for tuning.
FORCE_MANUAL_EXPOSURE = True
# Common OpenCV convention: 0.25 = manual, 0.75 = auto (varies by backend/driver).
AUTO_EXPOSURE_MANUAL_VALUE = 0.25
AUTO_EXPOSURE_AUTO_VALUE = 0.75

# Set to None to leave unchanged.
EXPOSURE = 300 # Often negative numbers (e.g. -5 to -10) for many webcams on Windows.
BRIGHTNESS = 0
GAIN = 20

# Optional per-camera overrides: index -> dict with keys exposure/brightness/gain
CAMERA_OVERRIDES = {}  # Example: cameras 2 and 3 get exposure -7

# Put your ffmpeg.exe path here
FFMPEG_PATH = r"C:\Users\bkkla\ffmpeg-2026-02-26-git-6695528af6-essentials_build\ffmpeg-2026-02-26-git-6695528af6-essentials_build\bin\ffmpeg.exe"
# ============================================

stop_event = threading.Event()
latest_frames = {}
latest_seqs = {}
frame_locks = {}
ffmpeg_processes = {}


def start_ffmpeg(filename, fps):
    if not os.path.exists(FFMPEG_PATH):
        raise FileNotFoundError(f"FFmpeg not found at: {FFMPEG_PATH}")

    command = [
        FFMPEG_PATH,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        FFMPEG_CODEC,
        "-preset",
        "p4",
        "-b:v",
        BITRATE,
        "-pix_fmt",
        "yuv420p",
        filename,
    ]

    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


def configure_camera(cap, index):
    desired_fps = (
        OUTPUT_FPS
        if LONG_EXPOSURE_SECONDS and LONG_EXPOSURE_MODE.lower() == "hardware"
        else TARGET_FPS
    )
    cap.set(cv2.CAP_PROP_FPS, float(desired_fps))

    if FORCE_MANUAL_EXPOSURE:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXPOSURE_MANUAL_VALUE)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AUTO_EXPOSURE_AUTO_VALUE)

    override = CAMERA_OVERRIDES.get(index, {})
    exposure = override.get("exposure", EXPOSURE)
    brightness = override.get("brightness", BRIGHTNESS)
    gain = override.get("gain", GAIN)

    if exposure is not None:
        cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure))
    if brightness is not None:
        cap.set(cv2.CAP_PROP_BRIGHTNESS, float(brightness))
    if gain is not None:
        cap.set(cv2.CAP_PROP_GAIN, float(gain))

    

    # Print what the driver reports after setting (some drivers ignore or quantize values).
    print(
        f"Cam {index} props:"
        f" fps={cap.get(cv2.CAP_PROP_FPS)}"
        f" auto_exposure={cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}"
        f" exposure={cap.get(cv2.CAP_PROP_EXPOSURE)}"
        f" brightness={cap.get(cv2.CAP_PROP_BRIGHTNESS)}"
        f" gain={cap.get(cv2.CAP_PROP_GAIN)}"
    )


def camera_capture(index):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"Camera {index} failed to open.")
        return

    configure_camera(cap, index)

    seq = 0
    while not stop_event.is_set():
        ret, frame = cap.read()
        if ret:
            with frame_locks[index]:
                latest_frames[index] = frame
                seq += 1
                latest_seqs[index] = seq

    cap.release()
    print(f"Camera {index} capture stopped.")


# ---- Discover Cameras ----
graph = FilterGraph()
devices = graph.get_input_devices()


camera_indices = [i for i, name in enumerate(devices) if name == "HD Camera"]

if not camera_indices:
    print("No cameras found.")
    raise SystemExit(0)

print("Using cameras:", camera_indices)

# ---- Start Capture Threads ----
threads = []
for idx in camera_indices:
    latest_frames[idx] = None
    latest_seqs[idx] = 0
    frame_locks[idx] = threading.Lock()
    t = threading.Thread(target=camera_capture, args=(idx,), daemon=True)
    t.start()
    threads.append(t)

# ---- Start FFmpeg Writers ----
timestamp = time.strftime("%Y%m%d_%H%M%S")
for idx in camera_indices:
    filename = f"cam_{idx}_{timestamp}.mp4"
    ffmpeg_processes[idx] = start_ffmpeg(filename, OUTPUT_FPS)

if LONG_EXPOSURE_SECONDS and LONG_EXPOSURE_SECONDS > 0:
    print(
        f"Recording long-exposure: {LONG_EXPOSURE_SECONDS}s per frame"
        f" ({OUTPUT_FPS:.6g} fps), mode={LONG_EXPOSURE_MODE}, blend={SOFTWARE_BLEND}"
    )
else:
    print(f"Recording real-time: {OUTPUT_FPS:.6g} fps")
print("Press 'q' to stop.")

# ---- Master Frame Scheduler ----
def _compose_frame(accum_frame, count, fallback_frame):
    if count <= 0 or accum_frame is None:
        return fallback_frame
    if SOFTWARE_BLEND.lower() == "max":
        out = accum_frame
    else:
        out = accum_frame / float(count)
    return np.clip(out, 0, 255).astype(np.uint8)


def _apply_post(frame):
    if frame is None:
        return None
    if POST_CONTRAST is None or float(POST_CONTRAST) == 1.0:
        return frame
    # cv2.convertScaleAbs does: dst = saturate(|alpha*src + beta|)
    return cv2.convertScaleAbs(frame, alpha=float(POST_CONTRAST), beta=0.0)


def _write_all(pipe, data):
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = pipe.write(view[total:])
        if written is None:
            # Some file-like objects return None; assume all bytes were accepted.
            return
        if written <= 0:
            raise BrokenPipeError("Short write to ffmpeg stdin")
        total += written


def _normalize_for_ffmpeg(frame, idx):
    if frame is None:
        return None

    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    if frame.ndim != 3 or frame.shape[2] != 3:
        print(
            f"Bad frame format for camera {idx}: "
            f"shape={getattr(frame, 'shape', None)} dtype={getattr(frame, 'dtype', None)}"
        )
        return None

    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)

    if frame.shape[0] != HEIGHT or frame.shape[1] != WIDTH:
        frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)

    frame = np.ascontiguousarray(frame)
    expected_nbytes = int(WIDTH) * int(HEIGHT) * 3
    if frame.nbytes != expected_nbytes:
        print(
            f"Bad frame byte size for camera {idx}: "
            f"nbytes={frame.nbytes} expected={expected_nbytes} shape={frame.shape} dtype={frame.dtype}"
        )
        return None

    return frame


start_time = time.perf_counter()
frame_number = 0
next_output_time = start_time

last_seen_seq = {idx: 0 for idx in camera_indices}
accum = {idx: None for idx in camera_indices}
accum_count = {idx: 0 for idx in camera_indices}

is_software_long_exposure = bool(
    LONG_EXPOSURE_SECONDS
    and LONG_EXPOSURE_SECONDS > 0
    and LONG_EXPOSURE_MODE.lower() == "software"
)

try:
    while not stop_event.is_set():
        now = time.perf_counter()

        # Pull in newly captured frames and (optionally) accumulate them for software long exposure.
        for idx in camera_indices:
            with frame_locks[idx]:
                frame = latest_frames[idx]
                seq = latest_seqs[idx]

            if frame is None or seq == last_seen_seq[idx]:
                continue

            last_seen_seq[idx] = seq

            if is_software_long_exposure:
                frame_f = frame.astype(np.float32)
                if accum[idx] is None:
                    accum[idx] = frame_f.copy()
                else:
                    if SOFTWARE_BLEND.lower() == "max":
                        np.maximum(accum[idx], frame_f, out=accum[idx])
                    else:
                        accum[idx] += frame_f
                accum_count[idx] += 1

        if now >= next_output_time:
            for idx in camera_indices:
                process = ffmpeg_processes.get(idx)
                if process is None or process.poll() is not None:
                    print(f"FFmpeg process for camera {idx} exited early.")
                    stop_event.set()
                    break

                with frame_locks[idx]:
                    frame = latest_frames[idx]

                if frame is not None:
                    out_frame = frame
                    if is_software_long_exposure:
                        out_frame = _compose_frame(accum[idx], accum_count[idx], frame)
                        accum[idx] = None
                        accum_count[idx] = 0

                    out_frame = _apply_post(out_frame)
                    out_frame = _normalize_for_ffmpeg(out_frame, idx)
                    if out_frame is None:
                        continue

                    try:
                        _write_all(process.stdin, out_frame.tobytes())
                    except (BrokenPipeError, OSError) as exc:
                        print(f"FFmpeg write error on camera {idx}: {exc}")
                        stop_event.set()
                        break

                    cv2.imshow(f"Cam {idx}", out_frame)

            frame_number += 1
            next_output_time = start_time + frame_number * FRAME_INTERVAL
        else:
            # Keep the loop responsive but avoid burning CPU while waiting for the next output frame.
            time.sleep(min(0.01, max(0.0, next_output_time - now)))

        if cv2.waitKey(1) & 0xFF == ord("q"):
            stop_event.set()

except KeyboardInterrupt:
    stop_event.set()
finally:
    # ---- Shutdown ----
    stop_event.set()

    for t in threads:
        t.join(timeout=2)

    for idx, process in ffmpeg_processes.items():
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"FFmpeg for camera {idx} did not exit in time. Terminating.")
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    cv2.destroyAllWindows()

print(f"Saved {frame_number} output frames per camera.")
