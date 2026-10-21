"""Deeper marslog study: activity, camera mix, gaps/bursts, LMST time-of-day, MSL REMS weather.
Usage: python study/deep_study.py  -> charts + findings.json in study/out/deep/"""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(R, "study", "out", "deep"); os.makedirs(OUT, exist_ok=True)
F = {}
df = pd.read_csv(os.path.join(R, "data", "images.csv.gz"), low_memory=False)
df["lmst_h"] = df.date_taken_mars.str.extract(r"M(\d\d):(\d\d)").astype(float).pipe(lambda x: x[0] + x[1] / 60)
df["utc"] = pd.to_datetime(df.date_taken_utc, errors="coerce", utc=True, format="ISO8601")
df["recv"] = pd.to_datetime(df.date_received, errors="coerce", utc=True, format="ISO8601")
df["lat_h"] = (df.recv - df.utc).dt.total_seconds() / 3600
def save(f, n): f.tight_layout(); f.savefig(os.path.join(OUT, n), dpi=110); plt.close(f)
# 1 activity per sol
fig, axes = plt.subplots(2, 1, figsize=(11, 6))
for ax, (m, g) in zip(axes, df.groupby("mission")):
    lo, hi = g.sol.min(), g.sol.max()
    s = g.groupby("sol").size().reindex(range(lo, hi + 1), fill_value=0)
    slope = np.polyfit(s.index, s.values, 1)[0]
    roll = s.rolling(15, center=True, min_periods=5).mean()
    thr = s.median() + 3 * (s.quantile(.75) - s.quantile(.25))
    F[m] = dict(total=int(len(g)), sols_span=int(len(s)), sols_with_images=int((s > 0).sum()),
        zero_sols=[int(x) for x in s[s == 0].index], low_sols_lt10=[int(x) for x in s[(s > 0) & (s < 10)].index],
        mean=round(s.mean(), 1), median=float(s.median()), max_sol=int(s.idxmax()), max=int(s.max()),
        slope_per_sol=round(slope, 2), first30_mean=round(s.iloc[:30].mean(), 1), last30_mean=round(s.iloc[-30:].mean(), 1),
        bursts=[(int(k), int(v)) for k, v in s[s > thr].items()], burst_thr=round(thr, 1),
        cameras=g.camera.value_counts().head(10).to_dict(), n_cameras=int(g.camera.nunique()),
        utc_range=[str(g.utc.min()), str(g.utc.max())])
    ax.bar(s.index, s.values, color="#888", width=1); ax.plot(roll, "C0", lw=2, label="15-sol mean")
    ax.axhline(thr, ls="--", c="C3", lw=1, label="burst threshold")
    ax.set_title(f"{m}: images per sol (trend {slope:+.2f}/sol)"); ax.legend(fontsize=8)
save(fig, "activity_per_sol.png")
for m in F: F[m]["activity_series"] = df[df.mission == m].groupby("sol").size().to_dict()
# 2 camera mix over time (instrument families, 10-sol bins)
fam = lambda c: ("Mastcam-Z" if c.startswith("MCZ") else "Mastcam" if c.startswith("MAST") else "Navcam" if "NAV" in c
    else "Hazcam" if "HAZ" in c else "SHERLOC" if "SHERLOC" in c else "SuperCam/ChemCam" if ("SUPERCAM" in c or "CHEMCAM" in c)
    else "MAHLI" if c == "MAHLI" else "Other")
df["family"] = df.camera.map(fam)
fig, axes = plt.subplots(2, 1, figsize=(11, 6))
for ax, (m, g) in zip(axes, df.groupby("mission")):
    b = (g.sol // 10) * 10
    t = pd.crosstab(b, g.family, normalize="index") * 100
    t.plot.area(ax=ax, lw=0); ax.set_ylim(0, 100); ax.set_ylabel("% of images"); ax.set_title(f"{m}: camera family share, 10-sol bins"); ax.legend(fontsize=7, ncol=4)
    F[m]["family_share_bins"] = t.round(1).to_dict(orient="index")
    F[m]["family_total"] = g.family.value_counts().to_dict()
save(fig, "camera_mix_over_time.png")
# 3 time-of-day
fig, ax = plt.subplots(figsize=(11, 4))
for m, g in df.groupby("mission"):
    h = g.lmst_h.dropna().astype(int).value_counts(normalize=True).sort_index() * 100
    ax.plot(h.index, h.values, "o-", label=m)
    F[m]["lmst_hist_pct"] = h.round(2).to_dict()
    F[m]["lmst_night_pct_lt6_or_ge19"] = round(((g.lmst_h < 6) | (g.lmst_h >= 19)).mean() * 100, 1)
    F[m]["lmst_median"] = round(g.lmst_h.median(), 2)
    F[m]["lmst_peak_hour"] = int(h.idxmax())
    F[m]["downlink_latency_h_median"] = round(g.lat_h.median(), 1)
    F[m]["lmst_by_family_median"] = g.groupby("family").lmst_h.median().round(2).to_dict()
ax.set_xlabel("local mean solar time (hour)"); ax.set_ylabel("% of images"); ax.set_xticks(range(0, 24, 2)); ax.legend(); ax.set_title("Imaging by Mars local time")
save(fig, "time_of_day.png")
# 4 MSL weather
w = pd.DataFrame(json.load(open(os.path.join(R, "data", "msl", "weather.json")))).sort_values("sol")
w = w.dropna(subset=["ls"]).copy()
w["my"] = 31 + (w.ls.diff() < -180).cumsum()  # Curiosity landed MY31 (Ls~150)
v = w.dropna(subset=["max_temp_c", "min_temp_c", "pressure_pa"])
F["weather"] = dict(n_rows=len(w), n_valid=len(v), sol_range=[int(w.sol.min()), int(w.sol.max())],
    date_range=[w.terrestrial_date.min(), w.terrestrial_date.max()],
    max_hi=v.loc[v.max_temp_c.idxmax(), ["sol", "terrestrial_date", "max_temp_c", "ls"]].tolist(),
    min_lo=v.loc[v.min_temp_c.idxmin(), ["sol", "terrestrial_date", "min_temp_c", "ls"]].tolist(),
    p_hi=v.loc[v.pressure_pa.idxmax(), ["sol", "terrestrial_date", "pressure_pa", "ls"]].tolist(),
    p_lo=v.loc[v.pressure_pa.idxmin(), ["sol", "terrestrial_date", "pressure_pa", "ls"]].tolist(),
    opacity=w.atmo_opacity.value_counts().to_dict(),
    missing_sols_in_span=int(w.sol.max() - w.sol.min() + 1 - w.sol.nunique()))
v = v.assign(lsb=(v.ls // 30) * 30)
F["weather"]["by_ls30"] = v.groupby("lsb")[["max_temp_c", "min_temp_c", "pressure_pa"]].mean().round(1).to_dict(orient="index")
F["weather"]["by_my"] = v.groupby("my").agg(n=("sol", "size"), ls_min=("ls", "min"), ls_max=("ls", "max"),
    tmax=("max_temp_c", "mean"), tmin=("min_temp_c", "mean"), p=("pressure_pa", "mean")).round(1).to_dict(orient="index")
full = v.groupby("my").ls.agg(lambda x: x.max() - x.min() > 340)
vf = v[v.my.isin(full[full].index)]
for col in ["max_temp_c", "min_temp_c", "pressure_pa"]:
    # trend after removing seasonal cycle (Ls 10-deg climatology)
    clim = vf.groupby((vf.ls // 10))[col].transform("mean")
    an = vf[col] - clim
    F["weather"][f"{col}_anom_trend_per_MY"] = round(np.polyfit(vf.sol, an, 1)[0] * 668.6, 2)
F["weather"]["full_years"] = [int(x) for x in full[full].index]
fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
for my, g in v.groupby("my"):
    axes[0].plot(g.ls, g.max_temp_c, ".", ms=2, label=f"MY{my}"); axes[1].plot(g.ls, g.min_temp_c, ".", ms=2); axes[2].plot(g.ls, g.pressure_pa, ".", ms=2)
axes[0].set_ylabel("max °C"); axes[1].set_ylabel("min °C"); axes[2].set_ylabel("pressure Pa"); axes[2].set_xlabel("solar longitude Ls (°)")
axes[0].legend(ncol=8, fontsize=7, markerscale=4); axes[0].set_title("Curiosity REMS by season, one color per Mars year")
save(fig, "msl_weather_seasonal.png")
fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
axes[0].plot(v.sol, v.max_temp_c, ".", ms=1.5, label="max"); axes[0].plot(v.sol, v.min_temp_c, ".", ms=1.5, label="min"); axes[0].legend(); axes[0].set_ylabel("°C")
axes[1].plot(v.sol, v.pressure_pa, ".", ms=1.5, c="C2"); axes[1].set_ylabel("Pa"); axes[1].set_xlabel("MSL sol")
axes[0].set_title("Curiosity REMS full record"); save(fig, "msl_weather_timeseries.png")
# anomalies: implausible weather values
F["weather"]["suspicious"] = v[(v.max_temp_c > 20) | (v.min_temp_c < -110) | (v.pressure_pa < 600) | (v.pressure_pa > 1000) | (v.max_temp_c < v.min_temp_c)][["sol", "max_temp_c", "min_temp_c", "pressure_pa"]].values.tolist()
F["weather"]["daily_range_mean"] = round((v.max_temp_c - v.min_temp_c).mean(), 1)
F["dupe_ids"] = int(df.id.duplicated().sum())
F["m2020_weather"] = json.load(open(os.path.join(R, "data", "mars2020", "weather.json")))
json.dump(F, open(os.path.join(OUT, "findings.json"), "w"), indent=1, default=str)
print(json.dumps({k: {kk: vv for kk, vv in F[k].items() if kk not in ("activity_series", "family_share_bins")} if isinstance(F[k], dict) else F[k] for k in F}, indent=1, default=str))
# quiet-sol composition and LMST coverage
for m, g in df.groupby("mission"):
    s = g.groupby("sol").size(); q = s[s < 10].index
    F[m]["quiet_sol_cameras"] = g[g.sol.isin(q)].camera.value_counts().to_dict()
    F[m]["lmst_missing_by_camera"] = g.groupby("camera").lmst_h.apply(lambda x: round(x.isna().mean(), 2)).to_dict()
    F[m]["downlink_latency_h_median"] = round(g.lat_h.median(), 1)
json.dump(F, open(os.path.join(OUT, "findings.json"), "w"), indent=1, default=str)
print({m: (F[m]["quiet_sol_cameras"], F[m]["downlink_latency_h_median"], F[m]["utc_range"]) for m in ("mars2020", "msl")})
