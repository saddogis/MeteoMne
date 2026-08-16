import re
import json
import csv
import os
from datetime import datetime, timezone

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.meteo.co.me/Meteorologija/aws_m.php"
DATA_DIR = "data"
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")
STATION_HISTORY_DIR = os.path.join(DATA_DIR, "history")
MAX_POINTS_PER_STATION = 96  # otprilike poslednjih ~16-24h, zavisno od učestalosti izvještavanja stanice

FIELDNAMES = ["sifra", "tip", "stanica", "datum_vrijeme", "T", "RR", "vjetar", "smjer_kod", "udar"]


def fetch_raw():
    r = requests.get(URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    r.raise_for_status()
    return r.text


def extract_posljednje(html):
    m = re.search(r"var\s+posljednje\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        raise ValueError("Nisam pronašao 'posljednje' varijablu na stranici — struktura sajta se možda promijenila.")
    raw = m.group(1)
    raw = re.sub(r",\s*\]", "]", raw)
    raw = re.sub(r",\s*\}", "}", raw)
    return json.loads(raw)


def flatten(data):
    rows = []
    for tip, arr in data.items():
        for item in arr:
            padded = (list(item) + [""] * 9)[:9]
            code, tip2, naziv, dt_str, T, RR, wind, wind_dir, gust = padded
            rows.append({
                "sifra": code,
                "tip": tip2,
                "stanica": naziv,
                "datum_vrijeme": dt_str,
                "T": T,
                "RR": RR,
                "vjetar": wind,
                "smjer_kod": wind_dir,
                "udar": gust,
            })
    return rows


def load_existing_keys():
    keys = set()
    if os.path.exists(HISTORY_CSV):
        with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keys.add((row["sifra"], row["datum_vrijeme"]))
    return keys


def append_new(rows, existing_keys):
    os.makedirs(DATA_DIR, exist_ok=True)
    is_new_file = not os.path.exists(HISTORY_CSV)
    new_rows = [r for r in rows if (r["sifra"], r["datum_vrijeme"]) not in existing_keys]
    if new_rows:
        with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new_file:
                writer.writeheader()
            writer.writerows(new_rows)
    return new_rows


def _to_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def export_station_history():
    """Pravi mali JSON fajl po stanici sa poslednjih N tačaka (T, RR, vjetar), za grafikone."""
    if not os.path.exists(HISTORY_CSV):
        return
    by_station = {}
    with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            by_station.setdefault(row["sifra"], []).append(row)

    os.makedirs(STATION_HISTORY_DIR, exist_ok=True)
    for sifra, rows in by_station.items():
        trimmed = rows[-MAX_POINTS_PER_STATION:]
        points = []
        for r in trimmed:
            points.append({
                "dt": r["datum_vrijeme"],
                "T": _to_float(r.get("T")),
                "RR": _to_float(r.get("RR")),
                "vjetar": _to_float(r.get("vjetar")),
            })
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", sifra)
        with open(os.path.join(STATION_HISTORY_DIR, f"{safe_name}.json"), "w", encoding="utf-8") as out:
            json.dump(points, out, ensure_ascii=False)


def main():
    html = fetch_raw()
    data = extract_posljednje(html)
    rows = flatten(data)

    existing = load_existing_keys()
    new_rows = append_new(rows, existing)
    export_station_history()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stations": rows,
        }, f, ensure_ascii=False, indent=2)

    print(f"Ukupno stanica: {len(rows)}, novih zapisa dodato u istoriju: {len(new_rows)}")


if __name__ == "__main__":
    main()
