"""Fetch rover traverse (end-of-drive localization waypoints) from NASA's public MMGIS map feeds.

Sources (verified with curl, HTTP 200, GeoJSON):
  https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json   (Perseverance)
  https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json   (Curiosity)
Each feature = one rover localization (site/drive RMC) with sol, lat/lon, easting/northing (m),
elev_geoid (m, Mars geoid), roll/pitch/yaw/tilt (deg), dist_m (drive length) and dist_total_m.
Writes data/traverse/{mission}.json. Usage: python -m marslog.traverse
"""
import json, os
from .fetch import get

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "traverse")
SRC = {"mars2020": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
       "msl": "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json"}
KEEP = ["RMC", "site", "drive", "sol", "lat", "lon", "easting", "northing", "elev_geoid",
        "roll", "pitch", "yaw", "tilt", "dist_m", "dist_total_m"]


def main():
    os.makedirs(DATA, exist_ok=True)
    for m, u in SRC.items():
        try:
            fs = get(u)["features"]
        except Exception as e:  # keep previous cache on failure
            print(f"traverse {m}: fetch failed ({e}); keeping cache"); continue
        pts = []
        for f in fs:
            p = f["properties"]
            r = {k: p.get(k) for k in KEEP}
            for k in KEEP[4:]:
                if r[k] is not None and r[k] == -9999: r[k] = None
            pts.append(r)
        pts.sort(key=lambda r: (r["sol"], r["dist_total_m"] or 0))
        json.dump({"source": u, "n": len(pts), "points": pts}, open(os.path.join(DATA, f"{m}.json"), "w"), separators=(",", ":"))
        print(f"traverse {m}: {len(pts)} waypoints, sols {pts[0]['sol']}-{pts[-1]['sol']}")


if __name__ == "__main__":
    main()
