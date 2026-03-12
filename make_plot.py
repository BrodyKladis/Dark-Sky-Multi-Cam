import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

CSV_FILE = "detections.csv"
OUTPUT_VIDEO = "detections_3d.mp4"

TIME_WINDOW = 15     # seconds visible in animation
FPS = 30
DEPTH_SHRINK = -0.9  # 0..1, how much marker size shrinks over the time axis
PREVIEW = True

# ----------------------------
# Load data
# ----------------------------

df = pd.read_csv(CSV_FILE)

t = df["time"].values
x = df["x"].values
y = df["y"].values
p = df["p_value"].values

# convert p-value to significance scale
size = -np.log10(p + 1e-20)
size = size * 5

# normalize time start
t = t - t.min()

t_max = t.max()

# ----------------------------
# Setup plot
# ----------------------------

fig = plt.figure(figsize=(8,8))
ax = fig.add_subplot(111, projection="3d")

ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.set_zlabel("Time")

# View nearly down onto XY; time axis mostly goes away from the viewer.
ax.view_init(elev=70, azim=-80)

sc = ax.scatter([], [], [], s=[], c="red", depthshade=True)

# axis limits
ax.set_xlim(x.min(), x.max())
ax.set_ylim(y.min(), y.max())
ax.set_zlim(0, TIME_WINDOW)

# ----------------------------
# Animation update
# ----------------------------

def update(frame):

    current_time = frame / FPS

    mask = (t >= current_time - TIME_WINDOW) & (t <= current_time)

    xt = x[mask]
    yt = y[mask]
    tt = t[mask] - (current_time - TIME_WINDOW)
    st = size[mask]

    # Shrink markers as they move "away" along the time (Z) axis.
    depth = np.clip(tt / TIME_WINDOW, 0.0, 1.0) if TIME_WINDOW > 0 else 0.0
    scale = 1.0 - DEPTH_SHRINK * depth
    st = st * (scale * scale)

    # Update the existing scatter instead of clearing ax.collections (not supported on some matplotlib versions).
    sc._offsets3d = (xt, yt, tt)
    sc.set_sizes(st)

    ax.set_zlim(0, TIME_WINDOW)

    return (sc,)

# ----------------------------
# Run animation
# ----------------------------

frames = int((t_max + TIME_WINDOW) * FPS)

anim = FuncAnimation(
    fig,
    update,
    frames=frames,
    interval=1000/FPS
)

if PREVIEW:
    plt.show()

anim.save(
    OUTPUT_VIDEO,
    fps=FPS,
    dpi=200
)

print("Animation saved to", OUTPUT_VIDEO)
