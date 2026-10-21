"""Model bake-off for the heat model (1-sol and 7-sol ahead), walk-forward over the last 20% of sols.

python -m marslog.bakeoff [--fast]   # writes study/bakeoff/results.json + results.md
Optional deps: lightgbm, statsmodels, torch (skipped if missing).
"""
import json, sys, time, warnings
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from marslog.heat import load, TARGETS

warnings.filterwarnings("ignore")
LAGS = 7
N_FOLDS = 5
BIN = 10  # climatology Ls bin width (deg)


def clean(y, win=15, k=5.0, floor=8.0):
    """Causal robust outlier filter: flag a reading far from the median of the preceding `win` readings
    (MAD-scaled, with a floor in deg C). Uses only past data, so cleaning cannot leak the target."""
    past = y.shift(1).rolling(win, min_periods=5).median()
    med = past
    mad = (y - med).abs().shift(1).rolling(win * 4, min_periods=10).median() * 1.4826
    bad = (y - med).abs() > np.maximum(k * mad, floor)
    return y.mask(bad), int(bad.sum())


def grid(w, target, cleaned=False):
    g = pd.DataFrame({"sol": np.arange(int(w.sol.min()), int(w.sol.max()) + 1)})
    g = g.merge(w[["sol", "ls_unwrap", "pressure_pa", "elev_m", target]], on="sol", how="left")
    g["ls_unwrap"] = g.ls_unwrap.interpolate().bfill()
    g["ls"] = g.ls_unwrap % 360
    g["elev_m"] = g.elev_m.interpolate().bfill()
    g["y_raw"] = g[target]
    nbad = 0
    if cleaned:
        g["y_in"], nbad = clean(g[target])
    else:
        g["y_in"] = g[target]
    return g, nbad


def climatology(g, cut):
    """Seasonal mean by Ls bin, smoothed circularly, fit only on sols < cut (cleaned inputs)."""
    tr = g[(g.sol < cut) & g.y_in.notna()]
    b = (tr.ls // BIN).astype(int)
    m = tr.y_in.groupby(b).mean().reindex(range(360 // BIN))
    m = m.interpolate(limit_direction="both")
    sm = (m.shift(1, fill_value=m.iloc[-1]) + 2 * m + m.shift(-1, fill_value=m.iloc[0])) / 4
    centers = np.arange(360 // BIN) * BIN + BIN / 2
    xs = np.r_[centers - 360, centers, centers + 360]; ys = np.r_[sm.values] * 1
    ys = np.r_[ys, ys, ys]
    return lambda ls: np.interp(np.asarray(ls) % 360, xs, ys)


def features(g, clim, h):
    """Row i predicts y at sol s=g.sol[i] using only observations at sols <= s-h."""
    c = clim(g.ls.values)
    a = g.y_in - c  # anomaly of input series
    aff = a.ffill()
    obs_sol = g.sol.where(g.y_in.notna()).ffill()
    X = pd.DataFrame({"sol": g.sol, "clim": c})
    for k in range(1, LAGS + 1):
        X[f"a_lag{k}"] = aff.shift(h + k - 1)
    X["a_roll7"] = a.rolling(7, min_periods=1).mean().shift(h)
    X["a_roll30"] = a.rolling(30, min_periods=3).mean().shift(h)
    X["a_std7"] = a.rolling(7, min_periods=2).std().shift(h)
    X["y_last"] = g.y_in.ffill().shift(h)
    X["gap"] = (g.sol - h) - obs_sol.shift(h) + 1
    X["p_lag"] = g.pressure_pa.ffill().shift(h)
    X["p_anom7"] = (g.pressure_pa.ffill() - g.pressure_pa.ffill().rolling(30, min_periods=1).mean()).shift(h)
    r = np.radians(g.ls)
    X["sin1"], X["cos1"], X["sin2"], X["cos2"] = np.sin(r), np.cos(r), np.sin(2 * r), np.cos(2 * r)
    X["elev_m"] = g.elev_m.shift(h)
    X["y"] = g.y_raw
    X["y_in"] = g.y_in
    X["a_target"] = g.y_in - c
    return X


FEATS = [f"a_lag{k}" for k in range(1, LAGS + 1)] + ["a_roll7", "a_roll30", "a_std7", "gap", "p_lag", "p_anom7",
                                                      "sin1", "cos1", "sin2", "cos2", "elev_m", "clim"]

# ---------------- models: fit(train_df) -> predict(test_df) -> array of y predictions ----------------

def m_persistence(tr, te, **k):
    return te.y_last.values


def m_climatology(tr, te, **k):
    return te.clim.values


def m_blend(tr, te, **k):
    t = tr.dropna(subset=["a_lag1", "a_target"])
    x, y = t.a_lag1.values, t.a_target.values
    b = float((x * y).sum() / (x * x).sum())
    return te.clim.values + b * te.a_lag1.fillna(0).values


def _xy(tr):
    t = tr.dropna(subset=FEATS[:1] + ["a_target"])
    return t[FEATS], t.a_target.values


def m_ridge(tr, te, **k):
    X, y = _xy(tr); f = X.columns
    mu = X.mean()
    m = Ridge(alpha=1.0).fit(X.fillna(mu), y)
    return te.clim.values + m.predict(te[f].fillna(mu))


HGB_GRID = [dict(max_iter=it, learning_rate=lr, max_leaf_nodes=ml, min_samples_leaf=msl, l2_regularization=1.0)
            for it, lr in [(200, 0.03), (400, 0.03)] for ml in [7, 15, 31] for msl in [20, 60]]


def tune(tr, make):
    """Pick hyper-params on an inner time split (last 20% of the training window)."""
    t = tr.dropna(subset=["a_lag1", "a_target"])
    cut = t.sol.quantile(0.8)
    a, b = t[t.sol <= cut], t[t.sol > cut]
    best = None
    for p in make["grid"]:
        m = make["cls"](**p).fit(a[FEATS], a.a_target)
        e = np.mean(np.abs(m.predict(b[FEATS]) - b.a_target))
        if best is None or e < best[0]: best = (e, p)
    return best[1]


def m_hgb(tr, te, params=None, **k):
    X, y = _xy(tr)
    p = params or tune(tr, {"grid": HGB_GRID, "cls": lambda **q: HistGradientBoostingRegressor(random_state=0, **q)})
    m = HistGradientBoostingRegressor(random_state=0, **p).fit(X, y)
    m_hgb.last_params = p
    return te.clim.values + m.predict(te[FEATS])


def m_lgbm(tr, te, **k):
    import lightgbm as lgb
    grid = [dict(n_estimators=n, learning_rate=0.03, num_leaves=nl, min_child_samples=mc, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0)
            for n in [200, 500] for nl in [7, 15, 31] for mc in [20, 60]]
    p = tune(tr, {"grid": grid, "cls": lgb.LGBMRegressor})
    X, y = _xy(tr)
    m = lgb.LGBMRegressor(**p).fit(X, y)
    return te.clim.values + m.predict(te[FEATS])


def m_sarimax(tr, te, h=1, full=None, **k):
    """ARMA(2,1) on the anomaly series (seasonality removed by climatology), Kalman filter handles gaps.
    Parameters fit on the training window, then walk-forward h-step forecasts with fixed parameters."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    cut = te.sol.min()
    a = full.set_index("sol").a_target
    trs = a[a.index < cut]
    res = SARIMAX(trs.values, order=(2, 0, 1), trend="c").fit(disp=False)
    allres = res.apply(a.values)  # same params, filter through all data
    # h-step forecast from origin o made from filtered state at o: use predicted state via dynamic prediction
    out = []
    sols = te.sol.values
    idx0 = int(a.index[0])
    if h == 1:
        pr = allres.get_prediction().predicted_mean  # one-step-ahead (uses data <= s-1)
        out = pr[sols - idx0]
    else:
        pr = np.full(len(a), np.nan)
        for s in sols:
            i = s - idx0; o = i - h  # origin index: data up to and including o
            if o < 10: continue
            pr[i] = allres.get_prediction(start=o + 1, end=i, dynamic=0).predicted_mean[-1] if False else np.nan
        # efficient: filter once, then propagate each origin's filtered state h steps with the AR transition
        fs = allres.filter_results
        T, c = fs.transition[:, :, 0], fs.state_intercept[:, 0]
        Z, d = fs.design[0, :, 0], fs.obs_intercept[0, 0]
        st = fs.filtered_state  # (k, n): state at t given data <= t
        for s in sols:
            i = s - idx0; o = i - h
            x = st[:, o]
            for _ in range(h): x = T @ x + c
            pr[i] = Z @ x + d
        out = pr[sols - idx0]
    return te.clim.values + np.asarray(out)


def m_nn(tr, te, kind="mlp", **k):
    import torch, torch.nn as nn
    torch.manual_seed(0); torch.set_num_threads(4)
    X, y = _xy(tr)
    mu, sd = X.mean(), X.std().replace(0, 1)
    Xt = torch.tensor(((X.fillna(mu) - mu) / sd).values, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32)[:, None]
    nl = LAGS
    if kind == "mlp":
        net = nn.Sequential(nn.Linear(Xt.shape[1], 64), nn.ReLU(), nn.Dropout(0.1), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))
        fwd = net
    else:
        class G(nn.Module):
            def __init__(s):
                super().__init__(); s.g = nn.GRU(1, 24, batch_first=True); s.h = nn.Sequential(nn.Linear(24 + Xt.shape[1] - nl, 32), nn.ReLU(), nn.Linear(32, 1))
            def forward(s, x):
                seq = x[:, :nl].flip(1)[:, :, None]  # oldest -> newest
                _, hn = s.g(seq); return s.h(torch.cat([hn[0], x[:, nl:]], 1))
        net = G(); fwd = net
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-3)
    n = len(Xt); nv = n // 10; tri, vai = slice(0, n - nv), slice(n - nv, n)
    best, bstate, bad = 1e9, None, 0
    for ep in range(300):
        net.train(); perm = torch.randperm(n - nv)
        for j in range(0, n - nv, 128):
            b = perm[j:j + 128]; opt.zero_grad()
            loss = nn.functional.l1_loss(fwd(Xt[tri][b]), yt[tri][b]); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): v = nn.functional.l1_loss(fwd(Xt[vai]), yt[vai]).item()
        if v < best - 1e-4: best, bstate, bad = v, {kk: vv.clone() for kk, vv in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad > 20: break
    net.load_state_dict(bstate); net.eval()
    Xe = torch.tensor(((te[FEATS].fillna(mu) - mu) / sd).values, dtype=torch.float32)
    with torch.no_grad(): p = fwd(Xe).numpy()[:, 0]
    return te.clim.values + p


MODELS = {
    "persistence": m_persistence,
    "seasonal_climatology": m_climatology,
    "clim_persistence_blend": m_blend,
    "ridge_anomaly_lags": m_ridge,
    "hgb_anomaly_tuned": m_hgb,
    "lightgbm_anomaly_tuned": m_lgbm,
    "sarimax_arma21_anomaly": m_sarimax,
    "mlp_lag_window": lambda tr, te, **k: m_nn(tr, te, "mlp"),
    "gru_lag_window": lambda tr, te, **k: m_nn(tr, te, "gru"),
}


def evaluate(w, target, h, cleaned, models=MODELS, split=0.8, n_folds=N_FOLDS):
    g, nbad = grid(w, target, cleaned)
    valid = g[g.y_raw.notna()]
    cut0 = valid.sol.quantile(split)
    test_sols = valid.sol[valid.sol > cut0].values
    folds = np.array_split(test_sols, n_folds)
    preds = {m: [] for m in models}; ys, ss = [], []
    for f in folds:
        start = int(f[0])
        clim = climatology(g, start - h + 1)  # only obs available at the first origin of this fold
        X = features(g, clim, h)
        tr = X[(X.sol <= start - h) & X.y_in.notna() & X.a_lag1.notna()]
        te = X[X.sol.isin(f)]
        ys.append(te.y.values); ss.append(te.sol.values)
        for name, fn in models.items():
            preds[name].append(fn(tr, te, h=h, full=X[X.sol <= int(f[-1])]))
    y = np.concatenate(ys)
    res = {}
    for name in models:
        p = np.concatenate(preds[name]); ok = ~np.isnan(p)
        res[name] = {"mae": round(float(np.mean(np.abs(p[ok] - y[ok]))), 3), "n": int(ok.sum())}
    return {"test_sols": [int(test_sols.min()), int(test_sols.max())], "n_test": len(test_sols), "n_flagged": nbad, "models": res,
            "_pred": {k: np.concatenate(v) for k, v in preds.items()}, "_y": y, "_sol": np.concatenate(ss)}


def main(argv=None):
    w, _ = load(".")
    out = {"protocol": f"time-based split (last 20% of sols with an observation = test), {N_FOLDS}-fold expanding-window walk-forward refit "
                       "over the test period; features use only obs at sols <= s-h; climatology + hyper-params fit on training window only. "
                       "MAE always scored against the raw (uncleaned) observations.", "results": {}}
    for tgt in TARGETS:
        for cleaned in [False, True]:
            for h in [1, 7]:
                t0 = time.time()
                r = evaluate(w, tgt, h, cleaned)
                key = f"{tgt}|h{h}|{'clean' if cleaned else 'raw'}"
                out["results"][key] = {k: v for k, v in r.items() if not k.startswith("_")}
                print(key, round(time.time() - t0), "s", {m: v["mae"] for m, v in r["models"].items()}, flush=True)
    finalize(out)


def finalize(out):
    from datetime import datetime, timezone
    out["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    names = list(next(iter(out["results"].values()))["models"])
    out["table"] = {n: {k: v["models"][n]["mae"] for k, v in out["results"].items()} for n in names}
    json.dump(out, open("study/bakeoff/results.json", "w"), indent=1)
    cols = list(out["results"])
    L = ["# Heat model bake-off", "", out["protocol"], "", "MAE in °C (lower is better). `clean` = causal robust outlier filter applied to inputs/training targets.", "",
         "| model | " + " | ".join(c.replace("_temp_c", "").replace("|", " ") for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for n in names:
        row = [out["table"][n][c] for c in cols]; L.append(f"| {n} | " + " | ".join(f"**{x}**" if x == min(out["table"][m][c] for m in names) else str(x) for x, c in zip(row, cols)) + " |")
    L += ["", "Flagged by cleaning: " + ", ".join(f"{c.split('|')[0]}: {out['results'][c]['n_flagged']}" for c in cols if c.endswith("|h1|clean"))]
    open("study/bakeoff/results.md", "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
