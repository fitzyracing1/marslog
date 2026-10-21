"""Heat model: learn + forecast Curiosity (REMS) daily max/min air temperature.

python -m marslog.heat train            # retrain, write study/heat/learned.{md,json} + site/heat.json + site/heat/learned.md
python -m marslog.heat predict --sol N  # retrain in-memory (seconds) and print prediction for sol N
"""
import argparse, json, math, os, sys
from datetime import datetime, timezone
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error

VERSION = "heat-1.0"
SOLS_PER_YEAR = 668.6
TARGETS = {"max_temp_c": "daily max air temp", "min_temp_c": "daily min air temp"}
LIN = ["sin1", "cos1", "sin2", "cos2", "mars_year", "elev_m"]
GB = LIN + ["ls", "lag_t", "lag7_t", "lag_p", "gap"]
HORIZON = 7


def load(root="."):
    w = pd.DataFrame(json.load(open(f"{root}/data/msl/weather.json")))
    w = w.dropna(subset=["ls"]).sort_values("sol").drop_duplicates("sol").reset_index(drop=True)
    my, yr, prev = [], 31, None  # Curiosity landed MY31 Ls150
    for ls in w.ls:
        if prev is not None and prev > 300 and ls < 60: yr += 1
        my.append(yr); prev = ls
    w["mars_year"] = my
    w["ls_unwrap"] = (w.mars_year - 31) * 360 + w.ls
    t = json.load(open(f"{root}/data/traverse/msl.json"))["points"]
    ts = np.array([p["sol"] for p in t]); te = np.array([p["elev_geoid"] for p in t])
    o = np.argsort(ts); ts, te = ts[o], te[o]
    w["elev_m"] = np.interp(w.sol, ts, te)
    return w, (ts, te)


def harm(df):
    r = np.radians(df.ls)
    df["sin1"], df["cos1"], df["sin2"], df["cos2"] = np.sin(r), np.cos(r), np.sin(2 * r), np.cos(2 * r)
    return df


def frame(w, target):
    """Rows with a valid target; lag features from the last obs >= 1 sol before (no leakage)."""
    d = harm(w.copy())
    ok = d[target].notna()
    v = d[target].where(ok).ffill().shift(1)
    d["lag_t"] = v
    d["lag7_t"] = d[target].where(ok).rolling(7, min_periods=1).mean().shift(1)
    d["lag_p"] = d.pressure_pa.ffill().shift(1)
    d["gap"] = d.sol - d.sol.where(ok).ffill().shift(1)
    return d[ok].dropna(subset=GB).reset_index(drop=True)


def fit(d, target, split=0.8):
    cut = d.sol.quantile(split)
    tr, te = d[d.sol <= cut], d[d.sol > cut]
    lin = Ridge(alpha=1.0).fit(tr[LIN], tr[target])
    gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0).fit(tr[GB], tr[target])
    clim = tr.groupby(tr.ls.round(-1) % 360)[target].mean()
    pc = te.ls.round(-1).mod(360).map(clim).fillna(tr[target].mean())
    pl, pg = lin.predict(te[LIN]), gb.predict(te[GB])
    mets = {"test_sols": [int(te.sol.min()), int(te.sol.max())], "n_train": len(tr), "n_test": len(te),
            "mae_persistence": round(mean_absolute_error(te[target], te.lag_t), 2),
            "mae_climatology": round(mean_absolute_error(te[target], pc), 2),
            "mae_linear_seasonal": round(mean_absolute_error(te[target], pl), 2),
            "mae_gradient_boosting": round(mean_absolute_error(te[target], pg), 2)}
    return tr, te, lin, gb, pg, mets


def ls_of_sol(w, sol):
    if sol <= w.sol.max():
        return float(np.interp(sol, w.sol, w.ls_unwrap) % 360)
    back = sol - SOLS_PER_YEAR * math.ceil((sol - w.sol.max()) / SOLS_PER_YEAR)
    return float((np.interp(back, w.sol, w.ls_unwrap) + 360) % 360)


def future_row(w, d, target, sol, trav):
    last = d.iloc[-1]; ls = ls_of_sol(w, sol)
    yrs = int(last.mars_year) + (1 if ls < last.ls - 180 else 0)
    hist = w[w[target].notna()]
    r = {"ls": ls, "mars_year": yrs, "elev_m": float(np.interp(sol, *trav)),
         "lag_t": float(hist[target].iloc[-1]), "lag7_t": float(hist[target].tail(7).mean()),
         "lag_p": float(w.pressure_pa.dropna().iloc[-1]), "gap": float(sol - hist.sol.iloc[-1])}
    return harm(pd.DataFrame([r]))


def learn(root="."):
    w, trav = load(root)
    out = {"model_version": VERSION, "last_trained": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "data": {"rows": len(w), "sols": [int(w.sol.min()), int(w.sol.max())], "last_obs_sol": int(w.dropna(subset=["max_temp_c"]).sol.max()),
                    "source": "NASA REMS (CAB outreach feed) + MMGIS traverse elevation"}, "targets": {}}
    for tgt in TARGETS:
        d = frame(w, tgt)
        tr, te, lin, gb, pg, mets = fit(d, tgt)
        res = te[tgt].values - pg
        q = np.quantile(res, [0.05, 0.95])
        pi = permutation_importance(gb, te[GB], te[tgt], n_repeats=5, random_state=0, scoring="neg_mean_absolute_error")
        imp = sorted(({"feature": f, "mae_increase_c": round(float(m), 2)} for f, m in zip(GB, pi.importances_mean)), key=lambda x: -x["mae_increase_c"])
        # full-data refit for curves + forecasts
        linA = Ridge(alpha=1.0).fit(d[LIN], d[tgt])
        gbA = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0).fit(d[GB], d[tgt])
        base = d[LIN].mean()
        grid = harm(pd.DataFrame({"ls": np.arange(0, 360, 30)}))
        for c in ["mars_year", "elev_m"]: grid[c] = base[c]
        curve = [{"ls": int(a), "temp_c": round(float(b), 1)} for a, b in zip(grid.ls, linA.predict(grid[LIN]))]
        coef = dict(zip(LIN, linA.coef_))
        # altitude: linear coef + GB partial dependence (low vs high elevation)
        lo, hi = d.elev_m.quantile([0.1, 0.9])
        Xl, Xh = d[GB].copy(), d[GB].copy(); Xl["elev_m"], Xh["elev_m"] = lo, hi
        pd_gb = float(gbA.predict(Xh).mean() - gbA.predict(Xl).mean())
        miss = te.assign(pred=pg, err=res).iloc[np.argsort(-np.abs(res))[:8]]
        r_all = d[tgt] - linA.predict(d[LIN]); z = (r_all - r_all.mean()) / r_all.std()
        anom = d.assign(resid=r_all, z=z)[np.abs(z) > 3].sort_values("z", key=abs, ascending=False).head(10)
        nxt = int(d.sol.max()) + 1
        fc = []
        for s in range(max(nxt, int(w.sol.max()) + 1), max(nxt, int(w.sol.max()) + 1) + HORIZON):
            p = float(gbA.predict(future_row(w, d, tgt, s, trav)[GB])[0])
            fc.append({"sol": s, "pred_c": round(p, 1), "lo90_c": round(p + q[0], 1), "hi90_c": round(p + q[1], 1)})
        out["targets"][tgt] = {
            "label": TARGETS[tgt], "metrics": mets, "interval90_residual_c": [round(float(x), 2) for x in q],
            "permutation_importance": imp, "seasonal_curve": curve,
            "seasonal_peak": max(curve, key=lambda x: x["temp_c"]), "seasonal_trough": min(curve, key=lambda x: x["temp_c"]),
            "altitude": {"linear_c_per_100m": round(float(coef["elev_m"]) * 100, 2), "elev_range_m": [round(float(d.elev_m.min())), round(float(d.elev_m.max()))],
                         "gb_effect_p10_to_p90_c": round(pd_gb, 2), "p10_p90_m": [round(float(lo)), round(float(hi))]},
            "mars_year_trend_c_per_year": round(float(coef["mars_year"]), 2),
            "biggest_misses": [{"sol": int(s), "date": dt, "actual_c": float(a), "pred_c": round(float(p), 1), "err_c": round(float(e), 1)} for s, dt, a, p, e in zip(miss.sol, miss.terrestrial_date, miss[tgt], miss.pred, miss.err)],
            "anomalies_z_gt3": [{"sol": int(s), "date": dt, "actual_c": float(a), "resid_c": round(float(r), 1), "z": round(float(zz), 1)} for s, dt, a, r, zz in zip(anom.sol, anom.terrestrial_date, anom[tgt], anom.resid, anom.z)],
            "forecast": fc,
        }
    return out, (w, trav)


def md(o):
    L = [f"# What the heat model learned ({o['model_version']})", "",
         f"Trained {o['last_trained']} on {o['data']['rows']} Curiosity REMS sols ({o['data']['sols'][0]}–{o['data']['sols'][1]}). "
         "Subject: Gale crater daily max/min air temperature. Time-based split: last 20% of sols held out.", ""]
    for t, r in o["targets"].items():
        m, a = r["metrics"], r["altitude"]
        L += [f"## {r['label']} (`{t}`)", "",
              f"**Accuracy (held-out sols {m['test_sols'][0]}–{m['test_sols'][1]}, n={m['n_test']}) – MAE °C:** "
              f"gradient boosting {m['mae_gradient_boosting']}, linear seasonal {m['mae_linear_seasonal']}, climatology {m['mae_climatology']}, persistence (yesterday) {m['mae_persistence']}.", "",
              f"- **Season:** warmest around Ls {r['seasonal_peak']['ls']}° ({r['seasonal_peak']['temp_c']} °C), coldest around Ls {r['seasonal_trough']['ls']}° ({r['seasonal_trough']['temp_c']} °C) — a swing of {round(r['seasonal_peak']['temp_c']-r['seasonal_trough']['temp_c'],1)} °C.",
              f"- **Altitude:** Curiosity climbed {a['elev_range_m'][0]} → {a['elev_range_m'][1]} m. Linear model: {a['linear_c_per_100m']} °C per 100 m; boosting: going from {a['p10_p90_m'][0]} to {a['p10_p90_m'][1]} m changes the prediction by {a['gb_effect_p10_to_p90_c']} °C (altitude is confounded with time/mission year).",
              f"- **Year-to-year drift** (linear, holding season+altitude): {r['mars_year_trend_c_per_year']} °C per Mars year.",
              f"- **90% interval** from held-out residuals: {r['interval90_residual_c'][0]} / +{r['interval90_residual_c'][1]} °C.", "",
              "| feature | MAE increase when shuffled (°C) |", "|---|---|"] + [f"| {i['feature']} | {i['mae_increase_c']} |" for i in r["permutation_importance"]] + [
              "", "Seasonal curve (linear model): " + ", ".join(f"Ls{c['ls']}: {c['temp_c']}" for c in r["seasonal_curve"]), "",
              "Biggest held-out misses: " + "; ".join(f"sol {b['sol']} ({b['date']}) actual {b['actual_c']} vs {b['pred_c']}" for b in r["biggest_misses"]), "",
              "Anomalies (|z|>3 vs seasonal model): " + ("; ".join(f"sol {b['sol']} ({b['date']}) {b['actual_c']} °C, z={b['z']}" for b in r["anomalies_z_gt3"]) or "none"), "",
              "Forecast: " + ", ".join(f"sol {f['sol']}: {f['pred_c']} [{f['lo90_c']}, {f['hi90_c']}]" for f in r["forecast"]), ""]
    L += ["## Caveats", "REMS outreach data (CAB) is rounded, has gaps and some suspect values; not science-grade (use PDS). "
          "Elevation is interpolated between MMGIS waypoints. Forecast Ls for future sols is copied from one Mars year earlier; "
          "lag features for future sols use the last observation, so uncertainty grows with gap."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="marslog.heat"); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("train"); p = sp.add_parser("predict"); p.add_argument("--sol", type=int, required=True)
    a = ap.parse_args(argv)
    o, (w, trav) = learn()
    if a.cmd == "train":
        os.makedirs("study/heat", exist_ok=True); os.makedirs("site/heat", exist_ok=True)
        text = md(o)
        for f in ["study/heat/learned.md", "site/heat/learned.md"]: open(f, "w").write(text)
        json.dump(o, open("study/heat/learned.json", "w"), indent=1)
        pub = {k: o[k] for k in ["model_version", "last_trained", "data"]}
        pub["predictions"] = {t: {"next_sols": r["forecast"], "metrics": r["metrics"], "interval90_residual_c": r["interval90_residual_c"]} for t, r in o["targets"].items()}
        pub["learned"] = "https://fitzyracing1.github.io/marslog/heat/learned.md"
        json.dump(pub, open("site/heat.json", "w"), indent=1)
        print(text)
    else:
        res = {"sol": a.sol, "model_version": o["model_version"], "ls": round(ls_of_sol(w, a.sol), 1)}
        obs = w[w.sol == a.sol]
        for t, r in o["targets"].items():
            d = frame(w, t)
            gbA = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0).fit(d[GB], d[t])
            row = d[d.sol == a.sol][GB] if (d.sol == a.sol).any() else future_row(w, d, t, a.sol, trav)[GB]
            p = float(gbA.predict(row)[0]); q = r["interval90_residual_c"]
            res[t] = {"pred_c": round(p, 1), "lo90_c": round(p + q[0], 1), "hi90_c": round(p + q[1], 1),
                      "observed_c": None if obs.empty or pd.isna(obs[t].iloc[0]) else float(obs[t].iloc[0])}
        print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
