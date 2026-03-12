import os
import threading
import time

import cv2
import numpy as np
from pygrabber.dshow_graph import FilterGraph

# Optional: DirectShow COM camera control (more reliable than OpenCV cap.set on many UVC cameras).
try:
    import comtypes
    import comtypes.client
    from comtypes import GUID, POINTER
    from ctypes import byref, c_long

    _HAVE_COMTYPES = True
except Exception:
    _HAVE_COMTYPES = False

# ================= SETTINGS =================
WIDTH = 1280
HEIGHT = 720
FOURCC = "MJPG"

# Exposure capture duration (seconds) for the "shot".
LONG_EXPOSURE_SECONDS = 50.0

# Stacking method:
# - "mean": averages frames (reduces noise; good general-purpose)
# - "max": per-pixel max (emphasizes trails/satellites/planes)
STACK_MODE = "mean"

# Output
OUTPUT_DIR = "astro_shots"
FILE_EXT = ".png"  # ".png" or ".tif" (tiff supported if your OpenCV build has it)

# Device selection
CAMERA_NAME_CONTAINS = ["HBV-W202012HD", "Walfront", "HD Camera"]
CAMERA_NAME_EXCLUDES = ["HP True Vision FHD Camera"]

# Image tweaks
ROTATE_180 = True
POST_CONTRAST = 50.0  # 1.0 unchanged, >1 more contrast

# Camera controls (best-effort; support varies by driver)
FORCE_MANUAL_EXPOSURE = True
AUTO_EXPOSURE_MANUAL_VALUE = 0.25
AUTO_EXPOSURE_AUTO_VALUE = 0.75
EXPOSURE = 5  # many UVC cams use negative values; set None to skip
GAIN = None
BRIGHTNESS = None
USE_DIRECTSHOW_COM_CONTROLS = True
# ============================================


_dshow_com_devices = None  # lazy init: list[(friendly_name, moniker)]


def _apply_rotate(frame):
    if frame is None or not ROTATE_180:
        return frame
    return cv2.rotate(frame, cv2.ROTATE_180)


def _apply_post(frame):
    if frame is None:
        return None
    if POST_CONTRAST is None or float(POST_CONTRAST) == 1.0:
        return frame
    return cv2.convertScaleAbs(frame, alpha=float(POST_CONTRAST), beta=0.0)


def _ensure_dshow_devices():
    global _dshow_com_devices
    if _dshow_com_devices is not None:
        return _dshow_com_devices

    _dshow_com_devices = []
    if not (_HAVE_COMTYPES and USE_DIRECTSHOW_COM_CONTROLS):
        return _dshow_com_devices

    try:
        comtypes.client.GetModule("quartz.dll")
        from comtypes.gen import QuartzTypeLib as q  # type: ignore

        CLSID_VideoInputDeviceCategory = GUID("{860BB310-5D01-11D0-BD3B-00A0C911CE86}")
        dev_enum = comtypes.client.CreateObject(q.SystemDeviceEnum, interface=q.ICreateDevEnum)
        enum_moniker = dev_enum.CreateClassEnumerator(CLSID_VideoInputDeviceCategory, 0)
        if not enum_moniker:
            return _dshow_com_devices

        while True:
            fetched = c_long()
            moniker = POINTER(q.IMoniker)()
            hr = enum_moniker.Next(1, byref(moniker), byref(fetched))
            if hr != 0 or fetched.value == 0:
                break

            try:
                bag = moniker.BindToStorage(None, None, q.IPropertyBag._iid_)  # type: ignore[attr-defined]
                bag = bag.QueryInterface(q.IPropertyBag)  # type: ignore
                var = comtypes.automation.VARIANT()
                bag.Read("FriendlyName", byref(var), None)
                name = str(var.value)
                _dshow_com_devices.append((name, moniker))
            except Exception:
                continue
    except Exception:
        _dshow_com_devices = []

    return _dshow_com_devices


def _try_set_dshow_exposure(index, exposure_value, force_manual):
    if exposure_value is None:
        return False
    devices = _ensure_dshow_devices()
    if not devices or index < 0 or index >= len(devices):
        return False

    try:
        from comtypes.gen import QuartzTypeLib as q  # type: ignore

        _name, moniker = devices[index]
        filt = moniker.BindToObject(None, None, q.IBaseFilter._iid_)  # type: ignore[attr-defined]
        filt = filt.QueryInterface(q.IBaseFilter)  # type: ignore
        cam_ctrl = filt.QueryInterface(q.IAMCameraControl)  # type: ignore

        CameraControl_Exposure = 4
        CameraControl_Flags_Auto = 0x0001
        CameraControl_Flags_Manual = 0x0002
        flags = CameraControl_Flags_Manual if force_manual else CameraControl_Flags_Auto

        hr = cam_ctrl.Set(CameraControl_Exposure, int(exposure_value), int(flags))
        return hr == 0
    except Exception:
        return False


def _discover_camera_indices():
    graph = FilterGraph()
    devices = graph.get_input_devices() or []
    if not devices:
        return [], []

    excludes = [s.lower() for s in (CAMERA_NAME_EXCLUDES or []) if s]
    allowed = [
        i
        for i, name in enumerate(devices)
        if not any(substr in (name or "").lower() for substr in excludes)
    ]

    if not CAMERA_NAME_CONTAINS:
        return allowed, devices

    includes = [s.lower() for s in (CAMERA_NAME_CONTAINS or []) if s]
    indices = [
        i
        for i, name in enumerate(devices)
        if any(substr in (name or "").lower() for substr in includes)
    ]
    allowed_set = set(allowed)
    return [i for i in indices if i in allowed_set], devices


def _configure_camera(cap, idx):
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*FOURCC))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(WIDTH))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(HEIGHT))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1.0)

    if FORCE_MANUAL_EXPOSURE:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, float(AUTO_EXPOSURE_MANUAL_VALUE))
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, float(AUTO_EXPOSURE_AUTO_VALUE))

    if EXPOSURE is not None:
        if not (_HAVE_COMTYPES and USE_DIRECTSHOW_COM_CONTROLS and _try_set_dshow_exposure(idx, EXPOSURE, FORCE_MANUAL_EXPOSURE)):
            cap.set(cv2.CAP_PROP_EXPOSURE, float(EXPOSURE))

    if GAIN is not None:
        cap.set(cv2.CAP_PROP_GAIN, float(GAIN))
    if BRIGHTNESS is not None:
        cap.set(cv2.CAP_PROP_BRIGHTNESS, float(BRIGHTNESS))

    print(
        f"Cam {idx} props:"
        f" auto_exposure={cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}"
        f" exposure={cap.get(cv2.CAP_PROP_EXPOSURE)}"
        f" brightness={cap.get(cv2.CAP_PROP_BRIGHTNESS)}"
        f" gain={cap.get(cv2.CAP_PROP_GAIN)}"
    )


def _capture_long_exposure(idx, device_name, out_path, stop_event):
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"Camera {idx} failed to open.")
        return False

    _configure_camera(cap, idx)

    accum = None
    count = 0
    t_end = time.perf_counter() + float(LONG_EXPOSURE_SECONDS)

    while not stop_event.is_set() and time.perf_counter() < t_end:
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        frame = _apply_rotate(frame)
        frame_f = frame.astype(np.float32)

        if accum is None:
            accum = frame_f.copy()
        else:
            if STACK_MODE.lower() == "max":
                np.maximum(accum, frame_f, out=accum)
            else:
                accum += frame_f
        count += 1

    cap.release()

    if accum is None or count <= 0:
        print(f"Camera {idx}: no frames captured.")
        return False

    if STACK_MODE.lower() == "max":
        out = accum
    else:
        out = accum / float(count)

    out_u8 = np.clip(out, 0, 255).astype(np.uint8)
    out_u8 = _apply_post(out_u8)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ok = bool(cv2.imwrite(out_path, out_u8))
    if ok:
        print(f"Saved cam {idx} ({device_name}) -> {out_path} (frames={count})")
    else:
        print(f"Failed to write image for cam {idx} -> {out_path}")
    return ok


def main():
    indices, devices = _discover_camera_indices()
    if not indices:
        print("No cameras found.")
        if devices:
            print("Devices:", devices)
        raise SystemExit(0)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    print("Using cameras:", indices)
    print(f"Long exposure: {LONG_EXPOSURE_SECONDS}s, stack={STACK_MODE}, out={OUTPUT_DIR}")

    stop_event = threading.Event()
    threads = []
    results = {}

    for idx in indices:
        name = devices[idx] if 0 <= idx < len(devices) else f"cam_{idx}"
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)[:80]
        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}_idx{idx}_{timestamp}{FILE_EXT}")

        def runner(i=idx, n=name, p=out_path):
            results[i] = _capture_long_exposure(i, n, p, stop_event)

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.05)
    except KeyboardInterrupt:
        stop_event.set()

    for t in threads:
        t.join(timeout=2)

    ok_count = sum(1 for v in results.values() if v)
    print(f"Done. Saved {ok_count}/{len(indices)} shots.")


if __name__ == "__main__":
    main()

