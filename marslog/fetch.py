"""Fetch raw-image metadata and weather from public, no-auth mars.nasa.gov JSON APIs.

Sources (verified):
  Perseverance images: https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json
  Curiosity images:    https://mars.nasa.gov/api/v1/raw_image_items/?condition_1=msl:mission
  Perseverance MEDA:   https://mars.nasa.gov/rss/api/?feed=weather&category=mars2020&feedtype=json
  Curiosity REMS:      https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json
Only metadata + URLs are stored; no image binaries.
"""
import argparse, json, os, time, urllib.request, urllib.parse

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
UA = {"User-Agent": "marslog/0.1 (+https://github.com/fitzyracing1/marslog)"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def m2020_page(sol, page):
    u = ("https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json"
         f"&num=100&page={page}&order=sol+desc&condition_2={sol}:sol:gte&condition_3={sol}:sol:lte")
    d = get(u)
    out = []
    for i in d.get("images", []):
        c, f, x = i.get("camera", {}), i.get("image_files", {}), i.get("extended", {})
        out.append({"id": i["imageid"], "sol": i["sol"], "camera": c.get("instrument"),
                    "filter": c.get("filter_name"), "sample_type": i.get("sample_type"),
                    "date_taken_utc": i.get("date_taken_utc"), "date_taken_mars": i.get("date_taken_mars"),
                    "date_received": i.get("date_received"), "site": i.get("site"), "drive": i.get("drive"),
                    "mast_az": x.get("mastAz"), "mast_el": x.get("mastEl"), "dimension": x.get("dimension"),
                    "url_full": f.get("full_res"), "url_small": f.get("small"), "link": i.get("link")})
    return out, int(d.get("total_results", 0))


def msl_page(sol, page):
    u = ("https://mars.nasa.gov/api/v1/raw_image_items/?order=sol%20desc&per_page=100"
         f"&page={page}&condition_1=msl:mission&condition_2={sol}:sol:gte&condition_3={sol}:sol:lte")
    d = get(u)
    out = []
    for i in d.get("items", []):
        x = i.get("extended") or {}
        out.append({"id": i["imageid"], "sol": i["sol"], "camera": i.get("instrument"),
                    "filter": x.get("filter_name"), "sample_type": x.get("sample_type"),
                    "date_taken_utc": i.get("date_taken"), "date_taken_mars": x.get("lmst"),
                    "date_received": i.get("date_received"), "site": i.get("site"), "drive": i.get("drive"),
                    "mast_az": x.get("mast_az"), "mast_el": x.get("mast_el"), "dimension": i.get("subframe_rect"),
                    "url_full": i.get("url"), "url_small": None,
                    "link": f"https://mars.nasa.gov/msl/multimedia/raw-images/?id={i['id']}"})
    return out, int(d.get("total", 0))


MISSIONS = {"mars2020": m2020_page, "msl": msl_page}


def latest_sol(m):
    return (get(
        "https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&num=1&page=0&order=sol+desc"
    )["images"][0]["sol"] if m == "mars2020" else get(
        "https://mars.nasa.gov/api/v1/raw_image_items/?order=sol%20desc&per_page=1&page=0&condition_1=msl:mission"
    )["items"][0]["sol"])


def fetch_sol(m, sol):
    items, page = [], 0
    while True:
        got, total = MISSIONS[m](sol, page)
        items += got
        page += 1
        if not got or len(items) >= total or page > 60:
            break
    seen, uniq = set(), []
    for i in items:
        if i["id"] not in seen:
            seen.add(i["id"]); uniq.append(i)
    return sorted(uniq, key=lambda i: (i["camera"] or "", i["id"]))


def weather(m):
    u = f"https://mars.nasa.gov/rss/api/?feed=weather&category={m}&feedtype=json"
    d = get(u)
    rows = d.get("sols") or d.get("soles") or []
    def num(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    out = {}
    for r in rows:
        try: s = int(r["sol"])
        except (KeyError, ValueError): continue
        out[s] = {"sol": s, "terrestrial_date": r.get("terrestrial_date"), "season": r.get("season"),
                  "ls": num(r.get("ls")), "min_temp_c": num(r.get("min_temp")), "max_temp_c": num(r.get("max_temp")),
                  "pressure_pa": num(r.get("pressure")), "sunrise": r.get("sunrise"), "sunset": r.get("sunset"),
                  "atmo_opacity": r.get("atmo_opacity"), "source": u}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=10, help="how many sols back from latest to ensure cached")
    ap.add_argument("--refresh", type=int, default=3, help="re-fetch the N most recent sols (late downlinks)")
    ap.add_argument("--budget", type=int, default=1500, help="seconds time budget")
    ap.add_argument("--missions", default="mars2020,msl")
    a = ap.parse_args()
    t0 = time.time()
    for m in a.missions.split(","):
        d = os.path.join(DATA, m); os.makedirs(d, exist_ok=True)
        w = weather(m)
        json.dump([w[k] for k in sorted(w)], open(os.path.join(d, "weather.json"), "w"), separators=(",", ":"))
        top = latest_sol(m)
        for sol in range(top, max(top - a.backfill, -1), -1):
            p = os.path.join(d, f"{sol}.json")
            if os.path.exists(p) and sol <= top - a.refresh:
                continue
            if time.time() - t0 > a.budget:
                print("budget exhausted"); break
            items = fetch_sol(m, sol)
            if not items and not os.path.exists(p):
                continue
            new = {"mission": m, "sol": sol, "count": len(items), "weather": w.get(sol), "images": items}
            if os.path.exists(p):
                old = json.load(open(p))
                if old.get("images") == items and old.get("weather") == w.get(sol):
                    continue
                new["first_seen"] = old.get("first_seen")
            new.setdefault("first_seen", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            new["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            json.dump(new, open(p, "w"), separators=(",", ":"))
            print(m, sol, len(items))


if __name__ == "__main__":
    main()
