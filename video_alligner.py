import cv2
import numpy as np
import glob
import os

VIDEO_FOLDER = "recordings/*.mp4"

def get_first_frame(video_path):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None

def show_frames_side_by_side(frame1, frame2):
    h1, w1 = frame1.shape[:2]
    h2, w2 = frame2.shape[:2]
    max_h = max(h1, h2)
    total_w = w1 + w2
    canvas = np.zeros((max_h, total_w, 3), dtype=np.uint8)
    canvas[:h1, :w1] = frame1
    canvas[:h2, w1:w1+w2] = frame2
    return canvas

video_files = sorted(glob.glob(VIDEO_FOLDER))

if len(video_files) < 2:
    print("Need at least 2 videos.")
    exit()

# Use first video as reference
reference_frame = get_first_frame(video_files[0])
if reference_frame is None:
    print("Could not load reference frame.")
    exit()

# --- Manual selection upfront ---
num_frames = 3  # You can change this to select more frames
frame_indices = [0, 'middle', -1]  # Start, middle, end

reference_points = []  # List of lists: [[(x1, y1), (x2, y2)], ...] for each frame
video_points = {video: [] for video in video_files[1:]}

for i, idx in enumerate(frame_indices):
    # Get reference frame
    cap_ref = cv2.VideoCapture(video_files[0])
    total_ref = int(cap_ref.get(cv2.CAP_PROP_FRAME_COUNT))
    if idx == 'middle':
        frame_idx = total_ref // 2
    elif idx == -1:
        frame_idx = total_ref - 1
    else:
        frame_idx = idx
    cap_ref.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret_ref, ref_frame = cap_ref.read()
    cap_ref.release()
    if not ret_ref:
        print(f"Could not load reference frame at index {frame_idx}")
        continue

    ref_copy = ref_frame.copy()
    points_ref = []
    def mouse_callback_ref(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points_ref) < 2:
            points_ref.append((x, y))
            cv2.circle(ref_copy, (x, y), 5, (0, 255, 0), -1)
            cv2.imshow(f"Reference Frame {i+1}: Click 2 points", ref_copy)

    print(f"Frame {i+1}: Click 2 points in reference video (frame {frame_idx}).")
    cv2.imshow(f"Reference Frame {i+1}: Click 2 points", ref_copy)
    cv2.setMouseCallback(f"Reference Frame {i+1}: Click 2 points", mouse_callback_ref)
    while len(points_ref) < 2:
        cv2.waitKey(1)
    cv2.destroyWindow(f"Reference Frame {i+1}: Click 2 points")
    reference_points.append(points_ref)

    # For each other video, select 2 points in corresponding frame
    for v in video_files[1:]:
        cap_v = cv2.VideoCapture(v)
        total_v = int(cap_v.get(cv2.CAP_PROP_FRAME_COUNT))
        if idx == 'middle':
            frame_idx_v = total_v // 2
        elif idx == -1:
            frame_idx_v = total_v - 1
        else:
            frame_idx_v = idx
        cap_v.set(cv2.CAP_PROP_POS_FRAMES, frame_idx_v)
        ret_v, v_frame = cap_v.read()
        cap_v.release()
        if not ret_v:
            print(f"Could not load frame from {v} at index {frame_idx_v}")
            continue
        v_copy = v_frame.copy()
        points_v = []
        def mouse_callback_v(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(points_v) < 2:
                points_v.append((x, y))
                cv2.circle(v_copy, (x, y), 5, (0, 255, 0), -1)
                cv2.imshow(f"{os.path.basename(v)} Frame {i+1}: Click 2 points", v_copy)

        print(f"Frame {i+1}: Click SAME 2 points in {os.path.basename(v)} (frame {frame_idx_v}).")
        cv2.imshow(f"{os.path.basename(v)} Frame {i+1}: Click 2 points", v_copy)
        cv2.setMouseCallback(f"{os.path.basename(v)} Frame {i+1}: Click 2 points", mouse_callback_v)
        while len(points_v) < 2:
            cv2.waitKey(1)
        cv2.destroyWindow(f"{os.path.basename(v)} Frame {i+1}: Click 2 points")
        video_points[v].append(points_v)

# --- Process videos after selection ---
for v in video_files[1:]:
    print(f"Processing {v}...")
    transforms = []
    for i in range(len(reference_points)):
        pts_ref = np.array(reference_points[i], dtype=np.float32)
        pts_v = np.array(video_points[v][i], dtype=np.float32)
        # Estimate similarity transform (rotation, translation, scale)
        M, _ = cv2.estimateAffinePartial2D(pts_v, pts_ref, method=cv2.LMEDS)
        transforms.append(M)

    # Interpolate transforms for all frames
    cap_v = cv2.VideoCapture(v)
    total_v = int(cap_v.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap_v.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap_v.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap_v.get(cv2.CAP_PROP_FPS)
    output_name = os.path.splitext(v)[0] + "_manual_aligned.mp4"
    out = cv2.VideoWriter(
        output_name,
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps,
        (width, height)
    )
    # Calculate frame indices for interpolation
    indices = []
    for idx in frame_indices:
        if idx == 'middle':
            indices.append(total_v // 2)
        elif idx == -1:
            indices.append(total_v - 1)
        else:
            indices.append(idx)

    # Linear interpolation between transforms
    for f in range(total_v):
        # Find which two keyframes this frame is between
        if f <= indices[0]:
            M = transforms[0]
        elif f >= indices[-1]:
            M = transforms[-1]
        else:
            for j in range(1, len(indices)):
                if indices[j-1] < f <= indices[j]:
                    alpha = (f - indices[j-1]) / (indices[j] - indices[j-1])
                    M = (1-alpha)*transforms[j-1] + alpha*transforms[j]
                    break
        ret, frame = cap_v.read()
        if not ret:
            break
        aligned = cv2.warpAffine(frame, M, (width, height))
        out.write(aligned)
    cap_v.release()
    out.release()
    print(f"Saved aligned video: {output_name}")