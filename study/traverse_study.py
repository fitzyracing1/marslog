"""Traverse / slope-driving study for Perseverance + Curiosity from cached MMGIS waypoints.
Usage: python study/traverse_study.py -> charts + findings.json in study/out/traverse/
Note: the public feeds give end-of-drive localizations per sol, not timestamps per drive segment,
so true per-drive speed is NOT available; we use distance per drive and distance per driving sol."""
import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(R, "study", "out", "traverse"); os.makedirs(OUT, exist_ok=True)
NAMES = {"mars2020": "Perseverance", "msl": "Curiosity"}
BINS = [-100, -10, -5, -2, 2, 5, 10, 100]
LAB = ["<-10%", "-10..-5", "-5..-2", "flat ±2", "2..5", "5..10", ">10%"]
F = {}
def save(f, n): f.tight_layout(); f.savefig(os.path.join(OUT, n), dpi=110); plt.close(f)

def drives(m):
    p = pd.DataFrame(json.load(open(os.path.join(R, "data", "traverse", f"{m}.json")))["points"])
    p = p.dropna(subset=["elev_geoid", "easting", "northing"]).reset_index(drop=True)
    d = pd.DataFrame({"sol": p.sol[1:].values, "from": p.RMC[:-1].values, "to": p.RMC[1:].values,
        "dist_m": p.dist_m[1:].values, "dz_m": np.diff(p.elev_geoid.values),
        "chord_m": np.hypot(np.diff(p.easting.values), np.diff(p.northing.values)),
        "elev_end": p.elev_geoid[1:].values, "tilt_end": p.tilt[1:].values})
    d["dist_m"] = d.dist_m.fillna(d.chord_m)
    d = d[(d.dist_m >= 1)].copy()                       # drop bumps / re-localizations
    d["grade_pct"] = 100 * d.dz_m / d[["dist_m", "chord_m"]].max(axis=1)
    d = d[d.grade_pct.abs() <= 60]                        # drop localization jumps
    d["cls"] = np.where(d.grade_pct < -2, "downhill", np.where(d.grade_pct > 2, "uphill", "flat"))
    d["bin"] = pd.cut(d.grade_pct, BINS, labels=LAB)
    return p, d

fig, axes = plt.subplots(2, 1, figsize=(11, 6)); fig2, ax2 = plt.subplots(1, 2, figsize=(11, 4))
fig3, ax3 = plt.subplots(1, 2, figsize=(11, 4))
for i, m in enumerate(NAMES):
    p, d = drives(m)
    d.to_csv(os.path.join(OUT, f"{m}_drives.csv"), index=False)
    ps = d.groupby("sol").agg(dist=("dist_m", "sum"), dz=("dz_m", "sum"))
    ps["grade"] = 100 * ps.dz / ps.dist
    ps["cls"] = np.where(ps.grade < -2, "downhill", np.where(ps.grade > 2, "uphill", "flat"))
    by = d.groupby("bin", observed=False).agg(n=("dist_m", "size"), mean_m=("dist_m", "mean"), median_m=("dist_m", "median"),
                                              total_km=("dist_m", lambda x: x.sum() / 1000), mean_tilt=("tilt_end", "mean")).round(2)
    bysol = ps.groupby("cls").dist.agg(["size", "mean", "median"]).round(1)
    dn = d[d.cls == "downhill"]
    F[m] = dict(waypoints=len(p), drives=len(d), sols=[int(p.sol.min()), int(p.sol.max())],
        total_km=round(d.dist_m.sum() / 1000, 2), odometer_km=round(p.dist_total_m.max() / 1000, 2),
        elev_start=round(p.elev_geoid.iloc[0], 1), elev_end=round(p.elev_geoid.iloc[-1], 1),
        elev_min=round(p.elev_geoid.min(), 1), elev_max=round(p.elev_geoid.max(), 1),
        net_gain_m=round(p.elev_geoid.iloc[-1] - p.elev_geoid.iloc[0], 1),
        total_climb_m=round(d.dz_m.clip(lower=0).sum(), 1), total_descent_m=round(-d.dz_m.clip(upper=0).sum(), 1),
        class_counts=d.cls.value_counts().to_dict(),
        class_km=(d.groupby("cls").dist_m.sum() / 1000).round(2).to_dict(),
        class_mean_drive_m=d.groupby("cls").dist_m.mean().round(1).to_dict(),
        class_median_drive_m=d.groupby("cls").dist_m.median().round(1).to_dict(),
        per_sol_by_class=bysol.to_dict(orient="index"), driving_sols=len(ps),
        mean_m_per_driving_sol=round(ps.dist.mean(), 1), median_m_per_driving_sol=round(ps.dist.median(), 1),
        by_bin=by.to_dict(orient="index"), corr_grade_vs_dist=round(d.grade_pct.rank().corr(d.dist_m.rank()), 3),
        steepest_descents=d[d.dist_m >= 10].nsmallest(5, "grade_pct")[["sol", "to", "dist_m", "dz_m", "grade_pct"]].round(2).values.tolist(),
        steepest_climbs=d[d.dist_m >= 10].nlargest(5, "grade_pct")[["sol", "to", "dist_m", "dz_m", "grade_pct"]].round(2).values.tolist(),
        longest_downhill=dn.nlargest(5, "dist_m")[["sol", "to", "dist_m", "dz_m", "grade_pct"]].round(2).values.tolist(),
        biggest_drop_drive=d.nsmallest(3, "dz_m")[["sol", "to", "dist_m", "dz_m", "grade_pct"]].round(2).values.tolist(),
        longest_drive=d.nlargest(3, "dist_m")[["sol", "to", "dist_m", "dz_m", "grade_pct"]].round(2).values.tolist())
    axes[i].plot(p.sol, p.elev_geoid, "-", lw=1.2); axes[i].set_ylabel("elevation m (geoid)")
    axes[i].set_title(f"{NAMES[m]}: elevation at each end-of-drive (net {F[m]['net_gain_m']:+.0f} m)"); axes[i].set_xlabel("sol")
    ax2[i].bar(LAB, by.mean_m.values, color=["#06c", "#39f", "#9cf", "#aaa", "#f96", "#f60", "#b00"])
    for k, n in enumerate(by.n.values): ax2[i].text(k, 0, f"n={n}", ha="center", va="bottom", fontsize=7)
    ax2[i].set_title(f"{NAMES[m]}: mean drive length by grade"); ax2[i].set_ylabel("m per drive"); ax2[i].tick_params(axis="x", labelsize=7)
    ax3[i].scatter(d.grade_pct, d.dist_m, s=4, alpha=.5); ax3[i].axvline(-2, c="#06c", lw=.8); ax3[i].axvline(2, c="#b00", lw=.8)
    ax3[i].set_xlabel("grade % (dz / distance)"); ax3[i].set_ylabel("drive m"); ax3[i].set_title(NAMES[m])
save(fig, "elevation_profile.png"); save(fig2, "drive_by_slope_bin.png"); save(fig3, "grade_vs_distance.png")

# pressure vs altitude (Curiosity REMS)
p, _ = drives("msl")
w = pd.DataFrame(json.load(open(os.path.join(R, "data", "msl", "weather.json")))).dropna(subset=["pressure_pa", "ls"]).sort_values("sol")
w = w[(w.pressure_pa > 600) & (w.pressure_pa < 1000)].copy()
el = p.groupby("sol").elev_geoid.last()
w["elev"] = np.interp(w.sol, el.index, el.values)
w["my"] = w.sol / 668.6
L = np.radians(w.ls.values)
H = np.column_stack([np.ones(len(w))] + [f(k * L) for k in (1, 2, 3) for f in (np.sin, np.cos)])
def fit(X):
    b, *_ = np.linalg.lstsq(X, w.pressure_pa.values, rcond=None); r = w.pressure_pa.values - X @ b
    return b, 1 - r.var() / w.pressure_pa.var()
b0, r0 = fit(np.column_stack([H, w.my]))
b1, r1 = fit(np.column_stack([H, w.my, w.elev]))
w["p_adj"] = w.pressure_pa - b1[-1] * (w.elev - w.elev.iloc[0])
Hs = 192 * 210 / 3.71  # scale height m (R_CO2, T~210K, g)
phys = -w.pressure_pa.mean() / Hs
elev_trend = np.polyfit(w.my, w.elev, 1)[0]
F["pressure_altitude"] = dict(n_sols=len(w), sol_range=[int(w.sol.min()), int(w.sol.max())],
    trend_no_elev_pa_per_my=round(b0[-1], 2), r2_no_elev=round(r0, 3),
    trend_with_elev_pa_per_my=round(b1[-2], 2), elev_coef_pa_per_m=round(b1[-1], 4), r2_with_elev=round(r1, 3),
    hydrostatic_pa_per_m=round(phys, 4), scale_height_m=round(Hs), elev_trend_m_per_my=round(elev_trend, 1),
    hydrostatic_expected_pa_per_my=round(phys * elev_trend, 2),
    share_explained_hydrostatic=round(phys * elev_trend / b0[-1], 2), share_explained_fit=round(1 - b1[-2] / b0[-1], 2),
    note="Seasonal cycle removed with 3 Ls harmonics; elevation interpolated from MMGIS waypoints; MY = sol/668.6.")
fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
resid0 = w.pressure_pa - np.column_stack([H]) @ b0[:-1]
ax[0].plot(w.sol, resid0, ".", ms=1.5, label="pressure minus seasonal fit"); ax[0].plot(w.sol, b0[-1] * w.my, "C3", label=f"trend {b0[-1]:.1f} Pa/MY")
ax[0].plot(w.sol, phys * (w.elev - w.elev.mean()) + resid0.mean(), "C2", label=f"hydrostatic from elevation ({phys:.3f} Pa/m)")
ax[0].legend(fontsize=8); ax[0].set_ylabel("Pa"); ax[0].set_title("Curiosity REMS: deseasonalized pressure vs climb")
ax[1].plot(w.sol, w.elev, "C1"); ax[1].set_ylabel("rover elevation m"); ax[1].set_xlabel("sol")
save(fig, "pressure_vs_altitude.png")
json.dump(F, open(os.path.join(OUT, "findings.json"), "w"), indent=1, default=str)
print(json.dumps({m: {k: F[m][k] for k in ("drives", "total_km", "net_gain_m", "class_counts")} for m in NAMES}), json.dumps(F["pressure_altitude"]))
