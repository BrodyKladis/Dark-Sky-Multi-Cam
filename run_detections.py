import torch
import cv2
import numpy as np
import os
import csv
from math import sqrt
from collections import deque
import time

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

VIDEO_FOLDER = "recordings_satellite/"
OUTPUT_VIDEO = "detections.mp4"
OUTPUT_CSV = "detections.csv"

alpha = 0.01
threshold = 1e-6
highlight_seconds = 3
preview = True
preview_max_fps = 30.0
calibration_seconds = 5.0
log_eps = 1e-30


def gaussian_pvalue(z):
    return 2 * (1 - 0.5 * (1 + torch.erf(torch.abs(z) / sqrt(2))))


class PixelNoiseModel:
    def __init__(self, cams, height, width):
        self.mu = torch.zeros((cams, height, width), device=device)
        self.var = torch.ones((cams, height, width), device=device)

    def update(self, frame):
        diff = frame - self.mu
        self.mu = (1 - alpha) * self.mu + alpha * frame
        self.var = (1 - alpha) * self.var + alpha * diff**2

    def p_values(self, frame):
        std = torch.sqrt(self.var + 1e-6)
        z = (frame - self.mu) / std
        return gaussian_pvalue(z)


def load_videos(folder):

    exts = (".mp4",".avi",".mov",".mkv")

    files = [
        os.path.join(folder,f)
        for f in os.listdir(folder)
        if f.lower().endswith(exts)
    ]

    files.sort()

    vids = [cv2.VideoCapture(f) for f in files]

    print("Loaded videos:")
    for f in files:
        print(" ",f)

    return vids


def load_frame(v):

    ret,frame = v.read()

    if not ret:
        return None

    gray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)

    return gray.astype(np.float32)


def spatial_filter(detections):

    kernel = torch.ones((1,1,3,3),device=device)

    conv = torch.nn.functional.conv2d(
        detections.float().unsqueeze(0).unsqueeze(0),
        kernel,
        padding=1
    )

    return (conv.squeeze() >= 3)


def main():

    videos = load_videos(VIDEO_FOLDER)
    cams = len(videos)

    height = int(videos[0].get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(videos[0].get(cv2.CAP_PROP_FRAME_WIDTH))
    fps = videos[0].get(cv2.CAP_PROP_FPS)

    # Total frames (best-effort): use the min across cameras so ETA matches loop termination.
    frame_counts = [int(v.get(cv2.CAP_PROP_FRAME_COUNT) or 0) for v in videos]
    total_frames = min([fc for fc in frame_counts if fc > 0], default=0) or None

    model = PixelNoiseModel(cams,height,width)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_VIDEO,fourcc,fps,(width,height))

    csvfile = open(OUTPUT_CSV,"w",newline="")
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(["time","x","y","p_value"])

    highlight_frames = int(highlight_seconds * fps)
    calibration_frames = int(calibration_seconds * fps)

    active_detections = []

    prev_detection_mask = torch.zeros((height, width), device=device, dtype=torch.bool)

    frame_index = 0
    start_time = time.perf_counter()
    last_report_t = start_time
    report_interval_frames = max(1, int(round(float(fps) if fps else 30.0)))
    last_preview_t = start_time

    while True:

        frames = []

        for v in videos:
            f = load_frame(v)
            if f is None:
                break
            frames.append(f)

        if len(frames) != cams:
            break

        frame = torch.tensor(np.stack(frames),device=device)

        p = model.p_values(frame)

        # Use log-probabilities to avoid underflow from multiplying many small p-values.
        log_p = torch.log(p.clamp_min(log_eps))
        log_p_joint = torch.sum(log_p, dim=0)
        log_threshold = float(np.log(threshold))

        detections = log_p_joint < log_threshold
        detections = spatial_filter(detections)

        if frame_index < calibration_frames:
            temporal = torch.zeros_like(detections, dtype=torch.bool)
            prev_detection_mask.zero_()
        else:
            temporal = detections & prev_detection_mask
            prev_detection_mask = detections

        coords = torch.nonzero(temporal)

        for y,x in coords:

            # Best-effort joint p-value for logging (may underflow to 0 for extremely small values).
            p_val = float(torch.exp(log_p_joint[y, x]).cpu())

            t = frame_index / fps

            csvwriter.writerow([t,int(x),int(y),p_val])

            active_detections.append({
                "x":int(x),
                "y":int(y),
                "expire":frame_index + highlight_frames
            })

        model.update(frame)

        combined = np.mean(frames,axis=0).astype(np.uint8)

        output = cv2.cvtColor(combined,cv2.COLOR_GRAY2BGR)

        active_detections = [
            d for d in active_detections
            if d["expire"] > frame_index
        ]

        for d in active_detections:

            cv2.circle(
                output,
                (d["x"],d["y"]),
                5,
                (0,0,255),
                -1
            )

        writer.write(output)

        if preview:
            now = time.perf_counter()
            if (now - last_preview_t) >= (1.0 / max(1.0, float(preview_max_fps))):
                last_preview_t = now
                cv2.imshow("detections_preview", output)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        frame_index += 1

        # Progress/ETA (prints about once per second of video, throttled by wall-clock too).
        now = time.perf_counter()
        if frame_index % report_interval_frames == 0 and (now - last_report_t) >= 0.5:
            last_report_t = now
            elapsed = now - start_time
            rate = frame_index / elapsed if elapsed > 1e-6 else 0.0

            if total_frames is not None and rate > 1e-6:
                remaining_frames = max(0, total_frames - frame_index)
                eta_seconds = remaining_frames / rate
                eta_clock = time.strftime("%H:%M:%S", time.localtime(time.time() + eta_seconds))
                print(
                    f"[{frame_index}/{total_frames}] "
                    f"{(100.0 * frame_index / total_frames):5.1f}% | "
                    f"{rate:6.1f} fps | "
                    f"ETA ~{eta_seconds:6.1f}s (at {eta_clock})"
                )
            else:
                print(f"[{frame_index}] {rate:6.1f} fps | elapsed {elapsed:6.1f}s")

    writer.release()
    csvfile.close()
    if preview:
        cv2.destroyAllWindows()

    print("Processing complete")
    print("Video saved to:",OUTPUT_VIDEO)
    print("CSV saved to:",OUTPUT_CSV)


if __name__ == "__main__":
    main()
