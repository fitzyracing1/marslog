"""Study starter: load the marslog cache with pandas and produce summary stats + charts.

Usage:  pip install pandas matplotlib && python study/study.py
Outputs to study/out/: images_per_camera_per_sol.csv, top_cameras.png, weather.png
"""
import glob, json, os
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(os.path.dirname(__file__), "out"); os.makedirs(OUT, exist_ok=True)

df = pd.read_csv(os.path.join(ROOT, "data", "images.csv.gz"), low_memory=False)
print(f"{len(df)} images, sols per mission:\n{df.groupby('mission').sol.agg(['min','max','nunique'])}\n")
pc = df.groupby(["mission", "sol", "camera"]).size().rename("images").reset_index()
pc.to_csv(os.path.join(OUT, "images_per_camera_per_sol.csv"), index=False)
for m, g in df.groupby("mission"):
    print(f"== {m}: top cameras\n{g.camera.value_counts().head(8)}\n")
    print(f"mean images/sol {g.groupby('sol').size().mean():.1f}, busiest sol {g.groupby('sol').size().idxmax()}\n")

fig, axes = plt.subplots(len(df.mission.unique()), 1, figsize=(11, 8), squeeze=False)
for ax, (m, g) in zip(axes[:, 0], pc.groupby("mission")):
    top = g.groupby("camera").images.sum().nlargest(6).index
    g[g.camera.isin(top)].pivot_table(index="sol", columns="camera", values="images", fill_value=0).plot.area(ax=ax, lw=0)
    ax.set_title(f"{m}: images per sol, top 6 cameras"); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "top_cameras.png"), dpi=110)

fig, ax = plt.subplots(figsize=(11, 4))
for m in ("mars2020", "msl"):
    p = os.path.join(ROOT, "data", m, "weather.json")
    if os.path.exists(p):
        w = pd.DataFrame(json.load(open(p))).dropna(subset=["max_temp_c"])
        ax.plot(w.sol, w.max_temp_c, ".", ms=2, label=f"{m} max")
        ax.plot(w.sol, w.min_temp_c, ".", ms=2, label=f"{m} min")
        print(f"{m} weather: {len(w)} sols, max temp mean {w.max_temp_c.mean():.1f}C, min temp mean {w.min_temp_c.mean():.1f}C")
ax.set_xlabel("sol (mission-specific)"); ax.set_ylabel("°C"); ax.legend(); ax.set_title("Air temperature by sol")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "weather.png"), dpi=110)
print("wrote", OUT)
