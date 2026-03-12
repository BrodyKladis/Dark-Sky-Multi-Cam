from glob import glob

import cv2
import numpy as np

# ----- PARAMETERS -----
video_folder = "recordings_processed/*.mp4"
video_files = sorted(glob(video_folder))

output_file = "cumulative_motion_simple.png"
colormap = cv2.COLORMAP_JET  # set to None to save grayscale

# Motion definition: abs difference between consecutive grayscale frames.
USE_ABS_DIFF = True


def main() -> int:
    if not video_files:
        raise RuntimeError(f"No videos found for glob: {video_folder!r}")

    caps = [cv2.VideoCapture(path) for path in video_files]
    try:
        if any(not cap.isOpened() for cap in caps):
            raise RuntimeError("One or more video files could not be opened.")

        prev_gray = []
        sizes = []
        for cap in caps:
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError("Failed to read first frame from one of the videos.")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            prev_gray.append(gray)
            sizes.append(gray.shape)

        h, w = sizes[0]
        if any(s != (h, w) for s in sizes):
            raise RuntimeError("Input videos do not share the same resolution.")

        cumulative = np.zeros((h, w), dtype=np.float32)

        while True:
            any_read = False
            for i, cap in enumerate(caps):
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                any_read = True

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
                if USE_ABS_DIFF:
                    motion = np.abs(gray - prev_gray[i])
                else:
                    motion = gray - prev_gray[i]
                prev_gray[i] = gray
                cumulative += motion

            if not any_read:
                break

        # Logarithmic normalization to enhance faint signals
        min_nonzero = np.min(cumulative[np.nonzero(cumulative)]) if np.any(cumulative > 0) else 1.0
        log_cumulative = np.log1p(cumulative / min_nonzero)
        log_max = log_cumulative.max() if log_cumulative.max() > 0 else 1.0
        norm_u8 = np.clip((log_cumulative / log_max) * 255.0, 0, 255).astype(np.uint8)

        if colormap is not None:
            out_img = cv2.applyColorMap(norm_u8, colormap)
        else:
            out_img = norm_u8

        if not cv2.imwrite(output_file, out_img):
            raise RuntimeError(f"Failed to write output image: {output_file}")

        print("Saved cumulative motion map to", output_file)
        return 0
    finally:
        for cap in caps:
            cap.release()


if __name__ == "__main__":
    raise SystemExit(main())

