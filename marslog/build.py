"""Build the changes layer + combined datasets + static GitHub Pages site into ./site."""
import csv, glob, gzip, html, json, os, time
from collections import Counter

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA, SITE = os.path.join(ROOT, "data"), os.path.join(ROOT, "site")
BASE = os.environ.get("SITE_URL", "https://fitzyracing1.github.io/marslog/")
NAMES = {"mars2020": "Perseverance (Mars 2020)", "msl": "Curiosity (MSL)"}
CSS = ("body{font:15px/1.5 system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#222}"
       "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:3px 8px;text-align:left}"
       "a{color:#b3410e}.up{color:#b00}.dn{color:#06c}code{background:#f4f4f4;padding:0 3px}")
E = html.escape


def page(title, body):
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{E(title)}</title><link rel=alternate type=application/atom+xml href='{BASE}feed.xml'>"
            f"<style>{CSS}</style><p><a href='{BASE}'>marslog</a></p><h1>{E(title)}</h1>{body}"
            "<hr><small>Metadata from public mars.nasa.gov APIs (NASA/JPL-Caltech; REMS by CAB, MEDA). "
            "Not affiliated with NASA. <a href='https://github.com/fitzyracing1/marslog'>source</a></small></html>")


def delta(a, b):
    if a is None or b is None: return None
    return round(a - b, 2)


def changes(mission):
    files = sorted(glob.glob(os.path.join(DATA, mission, "[0-9]*.json")), key=lambda p: int(os.path.basename(p)[:-5]))
    sols, prev_cams, all_cams = [], None, set()
    prev_w = None
    for p in files:
        d = json.load(open(p))
        cams = Counter(i["camera"] for i in d["images"])
        w = d.get("weather")
        entry = {"mission": mission, "sol": d["sol"], "count": d["count"], "cameras": dict(sorted(cams.items())),
                 "new_instruments": sorted(set(cams) - all_cams) if all_cams else [],
                 "returned_instruments": sorted(set(cams) - set(prev_cams or {})) if prev_cams is not None else [],
                 "camera_deltas": {c: cams.get(c, 0) - (prev_cams or {}).get(c, 0) for c in sorted(set(cams) | set(prev_cams or {}))} if prev_cams is not None else {},
                 "first_date_utc": min((i["date_taken_utc"] or "" for i in d["images"]), default=None),
                 "weather": w, "weather_delta": None, "first_seen": d.get("first_seen"), "updated": d.get("updated")}
        if w and prev_w:
            entry["weather_delta"] = {k: delta(w.get(k), prev_w.get(k)) for k in ("min_temp_c", "max_temp_c", "pressure_pa")}
        if w: prev_w = w
        all_cams |= set(cams); prev_cams = cams
        sols.append(entry)
    return sols


def traverse(mission):
    """Per-sol traverse summary from data/traverse/{mission}.json (MMGIS end-of-drive waypoints)."""
    p = os.path.join(DATA, "traverse", f"{mission}.json")
    if not os.path.exists(p): return {}, []
    pts = json.load(open(p))["points"]
    out, prev = {}, None
    for r in pts:
        dz = round(r["elev_geoid"] - prev["elev_geoid"], 2) if prev and r["elev_geoid"] is not None and prev["elev_geoid"] is not None else None
        dist = r["dist_m"] or 0
        g = round(100 * dz / dist, 2) if dz is not None and dist >= 1 else None
        d = dict(r, dz_m=dz, grade_pct=g, cls=None if g is None else "downhill" if g < -2 else "uphill" if g > 2 else "flat")
        out.setdefault(r["sol"], []).append(d); prev = r
    return out, [x for v in out.values() for x in v]


def traverse_html(ws):
    if not ws: return "<p>No rover localization (drive) reported for this sol in the public MMGIS traverse feed.</p>"
    rows = "".join(f"<tr><td>{E(w['RMC'])}</td><td>{w['lat']:.6f}, {w['lon']:.6f}</td><td>{w['easting']:.1f} / {w['northing']}</td>"
                   f"<td>{w['elev_geoid']:.1f}</td><td>{w['dist_m']}</td><td>{'' if w['dz_m'] is None else w['dz_m']}</td>"
                   f"<td>{'' if w['grade_pct'] is None else w['grade_pct']} {w['cls'] or ''}</td><td>{w['tilt']}</td><td>{w['dist_total_m']}</td></tr>" for w in ws)
    return ("<h2>Traverse</h2><table><tr><th>site_drive</th><th>lat, lon</th><th>easting / northing m</th><th>elev m</th>"
            f"<th>drive m</th><th>&Delta;elev m</th><th>grade %</th><th>tilt&deg;</th><th>odometer m</th></tr>{rows}</table>")


def fmt_d(v):
    if v is None: return ""
    return f"<span class={'up' if v > 0 else 'dn'}>{'+' if v > 0 else ''}{v}</span>" if v else "0"


def main():
    os.makedirs(SITE, exist_ok=True)
    trav_all = {}
    allsol, now = [], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    csvw = csv.writer(gzip.open(os.path.join(DATA, "images.csv.gz"), "wt", newline="", compresslevel=9))
    hdr = ["mission", "sol", "id", "camera", "filter", "sample_type", "date_taken_utc", "date_taken_mars",
           "date_received", "site", "drive", "mast_az", "mast_el", "dimension", "url_full", "url_small", "link"]
    csvw.writerow(hdr)
    for m in NAMES:
        for p in sorted(glob.glob(os.path.join(DATA, m, "[0-9]*.json"))):
            for i in json.load(open(p))["images"]:
                csvw.writerow([m] + [i.get(k) for k in hdr[1:]])
        ch = changes(m)
        json.dump(ch, open(os.path.join(DATA, m, "changes.json"), "w"), separators=(",", ":"))
        allsol += ch
        tr, trav_all[m] = traverse(m)
        for c in ch:
            rows = "".join(f"<tr><td>{E(k)}</td><td>{v}</td><td>{fmt_d(c['camera_deltas'].get(k))}</td></tr>" for k, v in c["cameras"].items())
            w = c["weather"]
            wt = (f"<p>Weather: min {w['min_temp_c']}&deg;C, max {w['max_temp_c']}&deg;C, pressure {w['pressure_pa']} Pa"
                  + (f" (&Delta; min {fmt_d(c['weather_delta']['min_temp_c'])}, max {fmt_d(c['weather_delta']['max_temp_c'])}, p {fmt_d(c['weather_delta']['pressure_pa'])})" if c['weather_delta'] else "")
                  + f" &middot; {E(str(w.get('terrestrial_date')))}</p>") if w else "<p>No weather report for this sol in the public feed.</p>"
            imgs = json.load(open(os.path.join(DATA, m, f"{c['sol']}.json")))["images"]
            lst = "".join(f"<li><a href='{E(i['link'] or '')}'>{E(i['id'])}</a> {E(i['camera'] or '')} <a href='{E(i['url_full'] or '')}'>img</a></li>" for i in imgs[:300])
            new = (f"<p><b>New instruments (first in cache):</b> {E(', '.join(c['new_instruments']))}</p>" if c["new_instruments"] else "")
            body = (f"<p>{c['count']} images &middot; first frame {E(c['first_date_utc'] or '')} UTC</p>{new}{wt}"
                    f"{traverse_html(tr.get(c['sol']))}<h2>Images per camera</h2><table><tr><th>camera</th><th>images</th><th>&Delta; vs prev sol</th></tr>{rows}</table>"
                    f"<p>Raw: <a href='{BASE}data/{m}/{c['sol']}.json'>{m}/{c['sol']}.json</a></p>"
                    f"<h2>Images{' (first 300)' if len(imgs) > 300 else ''}</h2><ul>{lst}</ul>")
            os.makedirs(os.path.join(SITE, m), exist_ok=True)
            open(os.path.join(SITE, m, f"sol-{c['sol']}.html"), "w").write(page(f"{NAMES[m]} — Sol {c['sol']}", body))
    json.dump({"generated": now, "source": {"mars2020": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
               "msl": "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json"},
               "note": "End-of-drive localizations; elev_geoid m; dist_m = drive length; grade = dz/dist_m. No per-drive timing/speed in source.",
               "missions": trav_all}, open(os.path.join(SITE, "traverse.json"), "w"), separators=(",", ":"))
    json.dump({"generated": now, "sols": allsol}, open(os.path.join(SITE, "data.json"), "w"))
    # index
    body = (f"<p>Daily cache of public NASA Mars rover raw-image metadata and weather, with a per-sol changelog. "
            f"Updated {now}. <a href='{BASE}data.json'>data.json</a> &middot; <a href='{BASE}traverse.json'>traverse.json</a> &middot; <a href='{BASE}feed.xml'>Atom</a> &middot; "
            f"<a href='{BASE}data/images.csv.gz'>images.csv.gz</a></p>")
    for m in NAMES:
        ch = [c for c in allsol if c["mission"] == m][::-1]
        if not ch: continue
        body += (f"<h2>{NAMES[m]}</h2><p>{len(ch)} sols, {sum(c['count'] for c in ch)} images cached.</p><table>"
                 "<tr><th>sol</th><th>images</th><th>cameras</th><th>new instr.</th><th>min/max &deg;C</th></tr>")
        for c in ch:
            w = c["weather"] or {}
            body += (f"<tr><td><a href='{BASE}{m}/sol-{c['sol']}.html'>{c['sol']}</a></td><td>{c['count']}</td><td>{len(c['cameras'])}</td>"
                     f"<td>{E(', '.join(c['new_instruments']))}</td><td>{w.get('min_temp_c', '')}/{w.get('max_temp_c', '')}</td></tr>")
        body += "</table>"
    open(os.path.join(SITE, "index.html"), "w").write(page("marslog — Mars rover data changelog", body))
    # feed
    recent = sorted(allsol, key=lambda c: c["updated"] or "", reverse=True)[:50]
    ent = "".join(f"<entry><id>{BASE}{c['mission']}/sol-{c['sol']}.html</id><title>{E(NAMES[c['mission']])} Sol {c['sol']}: {c['count']} images</title>"
                  f"<updated>{c['updated'] or now}</updated><link href='{BASE}{c['mission']}/sol-{c['sol']}.html'/>"
                  f"<summary>{E(', '.join(f'{k}: {v}' for k, v in c['cameras'].items()))}</summary></entry>" for c in recent)
    open(os.path.join(SITE, "feed.xml"), "w").write(f"<?xml version='1.0' encoding='utf-8'?><feed xmlns='http://www.w3.org/2005/Atom'>"
        f"<title>marslog</title><id>{BASE}</id><link href='{BASE}'/><updated>{now}</updated><author><name>marslog</name></author>{ent}</feed>")
    urls = [BASE] + [f"{BASE}{c['mission']}/sol-{c['sol']}.html" for c in allsol]
    open(os.path.join(SITE, "sitemap.xml"), "w").write("<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    open(os.path.join(SITE, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n")
    print(f"built {len(allsol)} sol pages")


if __name__ == "__main__":
    main()
