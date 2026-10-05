import argparse, csv, json, random

CITIES = [("Lviv","Ukraine"),("Kyiv","Ukraine"),("Odesa","Ukraine"),("Warsaw","Poland"),
          ("Krakow","Poland"),("Berlin","Germany"),("Munich","Germany"),("Paris","France"),
          ("Lyon","France"),("Vienna","Austria"),("Prague","Czechia"),("Budapest","Hungary"),
          ("Rome","Italy"),("Milan","Italy"),("Madrid","Spain"),("Lisbon","Portugal"),
          ("Riga","Latvia"),("Vilnius","Lithuania"),("Tallinn","Estonia"),("Oslo","Norway")]
AIRLINES = ["SkyNord","AeroVista","Blue Meridian","TransCarpa","Lumen Air","Falcon Jet","Orbit Airways","Zephyr Lines"]
SOURCES = ["AirWatch","FlightLog","PassengerReport"]

def generate(seed):
    r = random.Random(seed)
    params = {"seed": seed,
              "budget_threshold_eur": r.choice([79, 89, 99, 109, 119]),
              "long_flight_min": r.choice([150, 180, 210, 240])}
    rows, ids = [], set()
    for _ in range(r.randint(16, 20)):
        while True:
            fid = f"FL-{r.randint(1000, 9999)}"
            if fid not in ids:
                ids.add(fid); break
        a, b = r.sample(CITIES, 2)
        d = f"2026-{r.randint(3,9):02d}-{r.randint(1,28):02d}"
        if r.random() < 0.4: 
            y, m, dd = d.split("-"); d = f"{dd}.{m}.{y}"
        price = "" if r.random() < 0.15 else f"{r.randint(40, 260)}.{r.choice(['00','50','99'])}"
        note = f"delay={r.choice([10,15,25,40,55,90])};by={r.choice(SOURCES)}" if r.random() < 0.3 else ""
        rows.append([fid, r.choice(AIRLINES), a[0], a[1], b[0], b[1], d, r.randint(70, 320), price, note])
    
    for src in r.sample(rows, 2):
        dup = list(src)
        dup[0] = " " + src[0].lower() + " "
        dup[1] = src[1] + " "
        dup[2] = src[2].upper()
        rows.append(dup)
    r.shuffle(rows)
    return params, rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", default="flights.csv"); a = ap.parse_args()
    params, rows = generate(a.seed)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["flight_id","airline","from_city","from_country","to_city","to_country","dep_date","duration_min","price_eur","note"])
        w.writerows(rows)
    with open("params.json", "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2)
    print(f"{a.out}: {len(rows)} рядків; params.json: {params}")
