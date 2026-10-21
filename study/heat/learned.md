# What the heat model learned (heat-1.0)

Trained 2026-10-21T22:04:44+00:00 on 4745 Curiosity REMS sols (1–4995). Subject: Gale crater daily max/min air temperature. Time-based split: last 20% of sols held out.

## daily max air temp (`max_temp_c`)

**Accuracy (held-out sols 4024–4995, n=943) – MAE °C:** gradient boosting 3.4, linear seasonal 4.02, climatology 3.71, persistence (yesterday) 2.93.

- **Season:** warmest around Ls 210° (-1.5 °C), coldest around Ls 60° (-26.5 °C) — a swing of 25.0 °C.
- **Altitude:** Curiosity climbed -4521 → -3500 m. Linear model: 0.07 °C per 100 m; boosting: going from -4487 to -3673 m changes the prediction by -0.31 °C (altitude is confounded with time/mission year).
- **Year-to-year drift** (linear, holding season+altitude): 0.05 °C per Mars year.
- **90% interval** from held-out residuals: -5.32 / +7.34 °C.

| feature | MAE increase when shuffled (°C) |
|---|---|
| lag7_t | 2.66 |
| lag_t | 1.6 |
| cos1 | 0.36 |
| sin1 | 0.2 |
| ls | 0.11 |
| cos2 | 0.01 |
| mars_year | 0.0 |
| elev_m | 0.0 |
| gap | 0.0 |
| sin2 | -0.09 |
| lag_p | -0.12 |

Seasonal curve (linear model): Ls0: -12.2, Ls30: -20.3, Ls60: -26.5, Ls90: -26.5, Ls120: -19.8, Ls150: -10.4, Ls180: -3.5, Ls210: -1.5, Ls240: -2.6, Ls270: -3.8, Ls300: -4.5, Ls330: -6.6

Biggest held-out misses: sol 4774 (2026-01-10) actual -59.0 vs 0.3; sol 4155 (2024-04-14) actual -49.0 vs -3.9; sol 4198 (2024-05-28) actual -38.0 vs -2.3; sol 4153 (2024-04-12) actual -38.0 vs -5.5; sol 4111 (2024-02-29) actual -35.0 vs -2.8; sol 4218 (2024-06-18) actual -27.0 vs -0.2; sol 4110 (2024-02-28) actual 7.0 vs -6.4; sol 4806 (2026-02-12) actual -11.0 vs 2.0

Anomalies (|z|>3 vs seasonal model): sol 4774 (2026-01-10) -59.0 °C, z=-11.6; sol 2814 (2020-07-06) -53.0 °C, z=-10.1; sol 3496 (2022-06-07) -52.0 °C, z=-9.9; sol 2965 (2020-12-08) -54.0 °C, z=-9.5; sol 4155 (2024-04-14) -49.0 °C, z=-9.4; sol 3260 (2021-10-07) -67.0 °C, z=-8.8; sol 4153 (2024-04-12) -38.0 °C, z=-7.2; sol 4198 (2024-05-28) -38.0 °C, z=-6.9; sol 4111 (2024-02-29) -35.0 °C, z=-6.8; sol 3441 (2022-04-11) -31.0 °C, z=-5.9

Forecast: sol 4996: -7.3 [-12.6, 0.1], sol 4997: -6.9 [-12.2, 0.4], sol 4998: -7.0 [-12.3, 0.4], sol 4999: -7.0 [-12.3, 0.4], sol 5000: -8.0 [-13.3, -0.7], sol 5001: -8.0 [-13.3, -0.7], sol 5002: -7.8 [-13.1, -0.5]

## daily min air temp (`min_temp_c`)

**Accuracy (held-out sols 4024–4995, n=943) – MAE °C:** gradient boosting 2.51, linear seasonal 4.9, climatology 2.68, persistence (yesterday) 3.19.

- **Season:** warmest around Ls 210° (-69.0 °C), coldest around Ls 90° (-81.7 °C) — a swing of 12.7 °C.
- **Altitude:** Curiosity climbed -4521 → -3500 m. Linear model: -0.4 °C per 100 m; boosting: going from -4487 to -3673 m changes the prediction by -2.08 °C (altitude is confounded with time/mission year).
- **Year-to-year drift** (linear, holding season+altitude): 0.87 °C per Mars year.
- **90% interval** from held-out residuals: -5.28 / +2.81 °C.

| feature | MAE increase when shuffled (°C) |
|---|---|
| lag7_t | 0.95 |
| sin1 | 0.78 |
| lag_t | 0.09 |
| ls | 0.07 |
| cos1 | 0.03 |
| sin2 | 0.03 |
| cos2 | -0.0 |
| mars_year | 0.0 |
| elev_m | 0.0 |
| lag_p | -0.0 |
| gap | 0.0 |

Seasonal curve (linear model): Ls0: -74.1, Ls30: -77.5, Ls60: -80.7, Ls90: -81.7, Ls120: -79.5, Ls150: -75.2, Ls180: -71.1, Ls210: -69.0, Ls240: -69.0, Ls270: -70.0, Ls300: -70.9, Ls330: -71.9

Biggest held-out misses: sol 4780 (2026-01-16) actual -98.0 vs -63.7; sol 4781 (2026-01-17) actual -100.0 vs -65.9; sol 4844 (2026-03-23) actual -100.0 vs -66.7; sol 4817 (2026-02-23) actual -98.0 vs -65.3; sol 4823 (2026-03-01) actual -99.0 vs -66.3; sol 4835 (2026-03-14) actual -99.0 vs -67.1; sol 4792 (2026-01-28) actual -100.0 vs -68.3; sol 4847 (2026-03-26) actual -98.0 vs -67.0

Anomalies (|z|>3 vs seasonal model): sol 4792 (2026-01-28) -100.0 °C, z=-8.7; sol 4781 (2026-01-17) -100.0 °C, z=-8.6; sol 4844 (2026-03-23) -100.0 °C, z=-8.6; sol 2803 (2020-06-25) -100.0 °C, z=-8.5; sol 4852 (2026-03-31) -100.0 °C, z=-8.5; sol 4808 (2026-02-14) -99.0 °C, z=-8.4; sol 4821 (2026-02-27) -99.0 °C, z=-8.4; sol 4823 (2026-03-01) -99.0 °C, z=-8.4; sol 4094 (2024-02-11) -100.0 °C, z=-8.4; sol 4835 (2026-03-14) -99.0 °C, z=-8.4

Forecast: sol 4996: -72.2 [-77.5, -69.4], sol 4997: -69.3 [-74.6, -66.5], sol 4998: -70.2 [-75.5, -67.4], sol 4999: -70.2 [-75.5, -67.4], sol 5000: -68.8 [-74.1, -66.0], sol 5001: -68.8 [-74.1, -66.0], sol 5002: -68.7 [-74.0, -65.9]

## Caveats
REMS outreach data (CAB) is rounded, has gaps and some suspect values; not science-grade (use PDS). Elevation is interpolated between MMGIS waypoints. Forecast Ls for future sols is copied from one Mars year earlier; lag features for future sols use the last observation, so uncertainty grows with gap.
