# Heat model bake-off

time-based split (last 20% of sols with an observation = test), 5-fold expanding-window walk-forward refit over the test period; features use only obs at sols <= s-h; climatology + hyper-params fit on training window only. MAE always scored against the raw (uncleaned) observations.

MAE in °C (lower is better). `clean` = causal robust outlier filter applied to inputs/training targets.

| model | max h1 raw | max h7 raw | max h1 clean | max h7 clean | min h1 raw | min h7 raw | min h1 clean | min h7 clean |
|---|---|---|---|---|---|---|---|---|
| persistence | 2.931 | 4.138 | 2.702 | 3.614 | 3.189 | 3.52 | 2.305 | 2.534 |
| seasonal_climatology | 3.64 | 3.641 | 3.571 | 3.573 | 2.614 | 2.616 | 2.575 | 2.577 |
| clim_persistence_blend | 2.841 | 3.464 | 2.629 | 3.191 | 2.718 | 2.835 | 2.256 | 2.394 |
| ridge_anomaly_lags | 2.654 | 3.201 | 2.508 | **3.057** | 2.615 | 2.648 | 2.137 | 2.283 |
| hgb_anomaly_tuned | 2.632 | 3.42 | 2.505 | 3.163 | 2.795 | 3.133 | 2.165 | 2.331 |
| lightgbm_anomaly_tuned | 2.639 | 3.441 | 2.539 | 3.212 | 2.677 | 3.058 | 2.151 | 2.297 |
| sarimax_arma21_anomaly | 2.681 | 3.306 | 2.513 | 3.084 | 2.7 | 2.82 | **2.127** | **2.27** |
| mlp_lag_window | 2.625 | 3.154 | 2.508 | 3.106 | 2.301 | 2.431 | 2.173 | 2.345 |
| gru_lag_window | **2.504** | **3.133** | **2.485** | 3.077 | **2.22** | **2.383** | 2.166 | 2.333 |

Flagged by cleaning: max_temp_c: 35, min_temp_c: 62
