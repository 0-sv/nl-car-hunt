#!/usr/bin/env python3
"""Find cheap used cars in the Netherlands with a long APK, checked against RDW.

Pipeline: scrape (AutoScout24 + Marktplaats) -> rank (APK parsed from ad text)
-> verify (plate from ad page, APK/recall from RDW open data) -> report.
Standard library only. Run `carhunt.py <command> --help` for options.
"""
import argparse
import html as htmlmod
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DELAY = 0.4
TODAY = date.today()


def years_from_today(n):
    return date(TODAY.year + n, TODAY.month, min(TODAY.day, 28))

CITY = re.compile(
    r"\b(aygo|c1|107|108|matiz|spark|i10|picanto|twingo|ka\b|ka\+|up!?|smart|fortwo|forfour|panda|seicento|"
    r"cinquecento|500\b|wagon ?r|alto|splash|agila|cuore|sirion|charade|mii|citigo|lupo|arosa|atos|"
    r"pixo|celerio|kei|move|trevis|tico|ypsilon|c-zero|ion|i-miev|adam|karl|viva|micra|1007|kalos)", re.I)
SMALL = re.compile(
    r"\b(polo|fiesta|fiësta|121|clio|corsa|206|207|208|ibiza|fabia|swift|yaris|jazz|punto|colt|getz|i20|rio|"
    r"micra|c2|c3|saxo|fusion|mazda ?2|demio|logan|sandero|note|a2|a-klasse|a-class|mini|one|cooper|"
    r"justy|ignis|baleno|starlet|accent|pride|aveo|tigra|escort|fox|modus|streetwise|space star)\b", re.I)
REJECT = re.compile(
    r"(schade|defect|export|loopt niet|rijdt niet|start niet|startproblemen|motor kapot|motorschade|"
    r"versnellingsbak kapot|bak kapot|koppeling kapot|geen apk|zonder apk|apk verlopen|verlopen apk|"
    r"apk is verlopen|onderdelen|sloop|opknapper|handelsauto|handelaren|niet rijdbaar|cat ?[abc]\b|wok|"
    r"lekt|olie ?verbruik|koppakking|distributie kapot|afgekeurd|voor de handel|klusauto|project|lease|"
    r"overname|overnemen|cabrio|ruilen|gezocht|inkoop|wij kopen|te huur|verhuur)", re.I)
AUCTION = re.compile(r"(proveiling|veiling|bied mee|bieden kan alleen|geen minimumprijs|inzetprijs)", re.I)
ISSUES = re.compile(
    r"(schade aanwezig|zichtbare schade|motorschade|motor ?lampje|storingslampje|lampje brandt|brandt een lampje|"
    r"koppeling slipt|olie ?verbruik|verbruikt olie|lekt olie|olielek|roest door|doorgeroest|startproblemen|"
    r"start slecht|loopt onrustig|tikt|tikkend|rammelt|klappert|defect|kapot|piept|lekt)\b", re.I)
MONTHS = {"jan": 1, "feb": 2, "mrt": 3, "maa": 3, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}


def get(url, as_json=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "nl-NL,nl;q=0.9"})
    for attempt in range(3):
        try:
            body = urllib.request.urlopen(req, timeout=30).read()
            time.sleep(DELAY)
            return json.loads(body) if as_json else body.decode("utf-8", "replace")
        except Exception as e:
            print(f"retry {attempt + 1}: {url[:100]} {e}", file=sys.stderr, flush=True)
            time.sleep(3)
    return None


def write_jsonl(path, rows):
    # keep json.dumps' default ensure_ascii: Marktplaats cuts descriptions mid-emoji, and the lone surrogate breaks utf-8
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


# ---------- scrape: AutoScout24 ----------

def as24_page(params, page):
    q = {"atype": "C", "cy": "NL", "ustate": "N,U", "sort": "price", "desc": "0", **params, "page": page}
    html = get("https://www.autoscout24.nl/lst?" + urllib.parse.urlencode(q))
    if not html:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1))["props"]["pageProps"] if m else None


def scrape_as24(args):
    seen = {}
    total = None
    cap = 400  # the site serves at most 20 pages of 20 per search

    def harvest(params, first):
        n = first.get("numberOfResults", 0)
        for ls in [first["listings"]] + [
            (as24_page(params, p) or {}).get("listings", []) for p in range(2, min(20, (n + 19) // 20) + 1)
        ]:
            for l in ls:
                l.pop("images", None)
                seen[l["id"]] = l

    def slice_price(lo, hi, extra):
        nonlocal total
        params = {"pricefrom": lo, "priceto": hi, **extra}
        first = as24_page(params, 1)
        n = first.get("numberOfResults", 0) if first else 0
        if total is None:
            total = n
        print(f"as24 €{lo}-{hi} {extra or ''} -> {n}", file=sys.stderr, flush=True)
        if not first:
            return
        if n <= cap:
            harvest(params, first)
        elif hi > lo:
            mid = (lo + hi) // 2
            slice_price(lo, mid, extra)
            slice_price(mid + 1, hi, extra)
        elif "fregfrom" not in extra:
            # many ads share round prices like €1,500, so split those by first-registration year
            for y0, y1 in [(1950, 2000), (2001, 2003), (2004, 2005), (2006, 2007), (2008, 2009), (2010, 2100)]:
                slice_price(lo, hi, {**extra, "fregfrom": y0, "fregto": y1})
        else:
            harvest(params, first)

    slice_price(args.min_price, args.max_price, {})
    write_jsonl(args.out, seen.values())
    print(f"as24: {len(seen)} unique of {total} reported -> {args.out}")


# ---------- scrape: Marktplaats ----------

def scrape_mp(args):
    seen = {}
    cap = 4500  # the API serves at most 50 pages of 100 per search
    totals = []

    def fetch(lo, hi, offset, sort):
        by, order = sort
        q = [("l1CategoryId", "91"), ("limit", "100"), ("offset", str(offset)),
             ("attributeRanges[]", f"PriceCents:{lo * 100}:{hi * 100}"),
             ("sortBy", by), ("sortOrder", order), ("viewOptions", "list-view")]
        return get("https://www.marktplaats.nl/lrp/api/search?" + urllib.parse.urlencode(q), as_json=True)

    def slice_price(lo, hi, sort, top):
        d = fetch(lo, hi, 0, sort)
        n = d.get("totalResultCount", 0) if d else 0
        if top:
            totals.append(n)
        print(f"mp {sort[0]} €{lo}-{hi} -> {n}", file=sys.stderr, flush=True)
        if not d:
            return
        if n > cap and hi > lo:
            mid = (lo + hi) // 2
            slice_price(lo, mid, sort, False)
            slice_price(mid + 1, hi, sort, False)
            return
        batches = [d["listings"]]
        for off in range(100, min(n, 5000), 100):
            r = fetch(lo, hi, off, sort)
            if not r or not r["listings"]:
                break
            batches.append(r["listings"])
        for b in batches:
            for l in b:
                l.pop("imageUrls", None)
                l.pop("pictures", None)
                seen[l["itemId"]] = l

    # ads sharing a price reshuffle between pages, so one sort order skips ~10%; a second order fills most of it
    for sort in (("PRICE", "INCREASING"), ("SORT_INDEX", "DECREASING")):
        slice_price(args.min_price, args.max_price, sort, True)
    write_jsonl(args.out, seen.values())
    print(f"marktplaats: {len(seen)} unique of {max(totals or [0])} reported -> {args.out}")


# ---------- rank ----------

def apk_from_text(text):
    t = text.lower().replace("\n", " ")
    best = None
    for m in re.finditer(r"apk", t):
        win = t[m.start(): m.start() + 45]
        d = None
        m1 = re.search(r"(\d{1,2})[-/. ](\d{1,2})[-/. ](20\d\d|\d\d)\b", win)
        m2 = re.search(r"\b(\d{1,2})[-/. ](20\d\d)\b", win)
        m3 = re.search(r"(jan|feb|mrt|maa|mar|apr|mei|may|jun|jul|aug|sep|okt|oct|nov|dec)[a-z]*\.?\s*'?(20\d\d|\d\d)\b", win)
        m4 = re.search(r"\b(20\d\d)\b", win)
        try:
            if m1:
                y = int(m1.group(3)) + (2000 if len(m1.group(3)) == 2 else 0)
                d = date(y, int(m1.group(2)), int(m1.group(1)))
            elif m2:
                d = date(int(m2.group(2)), int(m2.group(1)), 15)
            elif m3:
                y = int(m3.group(2)) + (2000 if len(m3.group(2)) == 2 else 0)
                d = date(y, MONTHS[m3.group(1)], 15)
            elif m4:
                d = date(int(m4.group(1)), 6, 30)
        except ValueError:
            d = None
        if d and date(TODAY.year, 1, 1) <= d <= years_from_today(3):
            best = max(best, d) if best else d
    if best is None and re.search(
            r"(nieuwe|verse|nieuw|nwe|net|zojuist|vers) ?(gekeurde )?apk|apk ?(nieuw|vers)", t):
        return "new"
    return best


def months_until(d):
    return 12.0 if d == "new" else max(0.0, (d - TODAY).days / 30.44)


def normalise(l, src):
    if src == "mp":
        attrs = {a["key"]: a["value"] for a in l.get("attributes", [])}
        verticals = l.get("verticals") or []
        return {
            "src": "mp", "price": (l.get("priceInfo") or {}).get("priceCents", 0) / 100,
            "ptype": (l.get("priceInfo") or {}).get("priceType", ""),
            "title": l.get("title", ""),
            "text": l.get("title", "") + " " + (l.get("categorySpecificDescription") or l.get("description") or ""),
            "make": verticals[1] if len(verticals) > 1 else "", "model": attrs.get("model", ""),
            "year": attrs.get("constructionYear", ""), "km": attrs.get("mileage", ""),
            "fuel": attrs.get("fuel", ""), "city": (l.get("location") or {}).get("cityName", ""),
            "url": "https://www.marktplaats.nl" + l.get("vipUrl", ""),
        }
    v = l.get("vehicle", {})
    tr = l.get("tracking") or {}
    return {
        "src": "as24", "price": (l.get("price") or {}).get("priceRaw") or 0, "ptype": "FIXED",
        "title": l.get("title", ""),
        "text": " ".join([l.get("title", ""), v.get("modelVersionInput") or "", v.get("subtitle") or ""]),
        "make": v.get("make", ""), "model": v.get("model", ""), "year": tr.get("firstRegistration", "")[-4:],
        "km": tr.get("mileage", ""), "fuel": v.get("fuel", ""), "city": (l.get("location") or {}).get("city", ""),
        "url": "https://www.autoscout24.nl" + l.get("url", ""),
    }


def rank(args):
    rows = []
    for path in args.inputs:
        src = "mp" if "itemId" in open(path).readline() else "as24"
        for l in read_jsonl(path):
            r = normalise(l, src)
            name = f'{r["model"]} {r["title"]}'
            if not (args.min_price <= r["price"] <= args.max_price) or CITY.search(name) or REJECT.search(r["text"]):
                continue
            apk = apk_from_text(r["text"])
            if apk is None or months_until(apk) < args.min_months:
                continue
            ml = months_until(apk)
            r.update(apk=str(apk), months=round(ml, 1), per_month=round(r["price"] / ml), small=bool(SMALL.search(name)))
            rows.append(r)
    rows.sort(key=lambda r: r["per_month"])
    json.dump(rows, open(args.out, "w"), indent=1)
    print(f"ranked: {len(rows)} with a stated APK, {sum(not r['small'] for r in rows)} not small -> {args.out}")


# ---------- verify ----------

def rdw(plate):
    p = re.sub(r"[^A-Z0-9]", "", plate.upper())
    d = get(f"https://opendata.rdw.nl/resource/m9d7-ebf2.json?kenteken={p}", as_json=True)
    return d[0] if d else None


def verify(args):
    rows = json.load(open(args.input))
    cands = [r for r in rows if args.include_small or not r["small"]][: args.limit]
    out = []
    rdw_failures = 0
    for i, r in enumerate(cands):
        item = dict(r)
        page = get(r["url"]) or ""
        if r["src"] == "mp":
            plate = re.search(r'"kenteken":"([a-z0-9-]+)"', page)
            block = re.search(r'<div class="Description-module-description">(.*?)</div>', page, re.S)
            full = block.group(1) if block else ""
            item["sold"] = any(s in page for s in ('"isSold":true', '"status":"SOLD"', "Dit artikel is verkocht",
                                                   "Deze advertentie is niet meer beschikbaar"))
        else:
            plate = re.search(r'"licensePlate"\s*:\s*"([A-Za-z0-9-]+)"', page) or \
                re.search(r'"registrationNumber"\s*:\s*"([A-Za-z0-9-]+)"', page)
            block = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', page)
            try:
                full = json.loads('"' + block.group(1) + '"') if block else ""
            except ValueError:
                full = block.group(1)
            item["sold"] = False
        full = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htmlmod.unescape(full))).strip()
        item["full"] = full[:2000]
        item["auction"] = bool(AUCTION.search(full + " " + r["text"]))
        # "lekt" (leaks) also matches inside "elektrisch" (electric), which every equipment list contains
        scrubbed = re.sub(r"elektris\w*", "", full, flags=re.I)
        item["issues"] = sorted({m.group(0).lower() for m in ISSUES.finditer(scrubbed)})
        if plate:
            item["plate"] = plate.group(1)
            v = rdw(plate.group(1)) if rdw_failures < 3 else None
            rdw_failures = 0 if v else rdw_failures + 1
            if v:
                apk = v.get("vervaldatum_apk")
                item["rdw_apk"] = f"{apk[:4]}-{apk[4:6]}-{apk[6:]}" if apk else None
                item["rdw_model"] = f'{v.get("merk", "")} {v.get("handelsbenaming", "")}'.strip()
                item["rdw_first"] = v.get("datum_eerste_toelating", "")
                item["rdw_recall"] = v.get("openstaande_terugroepactie_indicator")
                item["rdw_export"] = v.get("export_indicator")
        out.append(item)
        if (i + 1) % 25 == 0:
            print(f"verified {i + 1}/{len(cands)}", file=sys.stderr, flush=True)
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"verified: {len(out)} ads, {sum('plate' in x for x in out)} with plate, "
          f"{sum(bool(x.get('rdw_apk')) for x in out)} with RDW APK -> {args.out}")
    if rdw_failures >= 3:
        print("WARNING: RDW stopped answering (opendata.rdw.nl); APK dates are unverified. "
              "Run `report --ad-apk` and say so.", file=sys.stderr)


# ---------- report ----------

def report(args):
    rows = json.load(open(args.input))
    seen, ok = set(), []
    dropped = {"sold": 0, "auction": 0, "no RDW APK": 0, "export": 0, "short APK": 0}
    for x in rows:
        key = x.get("plate") or x["url"]
        if key in seen:
            continue
        seen.add(key)
        x["apk_source"] = "RDW" if x.get("rdw_apk") else "ad"
        if not x.get("rdw_apk") and args.ad_apk:
            x["rdw_apk"] = x["apk"] if x["apk"] != "new" else years_from_today(1).isoformat()
        reason = ("sold" if x.get("sold") else "auction" if x.get("auction") else
                  "no RDW APK" if not x.get("rdw_apk") else "export" if x.get("rdw_export") == "Ja" else None)
        if not reason:
            mo = (date.fromisoformat(x["rdw_apk"]) - TODAY).days / 30.44
            if mo < args.min_months:
                reason = "short APK"
            else:
                x["rdw_months"] = round(mo, 1)
                x["rdw_per_month"] = round(x["price"] / mo)
                ok.append(x)
        if reason:
            dropped[reason] += 1
    ok.sort(key=lambda x: x["rdw_per_month"])
    json.dump(ok, open(args.out, "w"), indent=1)
    print(f"kept {len(ok)} cars ({sum(x['apk_source'] == 'RDW' for x in ok)} RDW-verified); dropped {dropped} -> {args.out}")
    print("€/mo  price  type apk        src  year  km       model                      city             recall issues  url")
    for x in ok[: args.top]:
        print(f'{x["rdw_per_month"]:>4} {x["price"]:>6.0f} {x["ptype"][:3]:3} {x["rdw_apk"]} {x["apk_source"]:4} {x["year"]:>5} '
              f'{str(x["km"]):>8} {x.get("rdw_model", "")[:26]:26} {x["city"][:16]:16} {x.get("rdw_recall") or "?":3} '
              f'{",".join(x["issues"])[:30]:30} {x["url"]}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def prices(sp):
        sp.add_argument("--max-price", type=int, default=1500)
        sp.add_argument("--min-price", type=int, default=300, help="below this, ads are mostly bait or wrecks")

    sp = sub.add_parser("scrape-as24", help="all AutoScout24 NL ads in the price range")
    prices(sp)
    sp.add_argument("--out", default="as24.jsonl")
    sp.set_defaults(fn=scrape_as24)

    sp = sub.add_parser("scrape-mp", help="all Marktplaats car ads in the price range")
    prices(sp)
    sp.add_argument("--out", default="mp.jsonl")
    sp.set_defaults(fn=scrape_mp)

    sp = sub.add_parser("rank", help="filter and rank by price per month of stated APK")
    sp.add_argument("inputs", nargs="+")
    prices(sp)
    sp.add_argument("--min-months", type=float, default=5, help="minimum stated APK months left")
    sp.add_argument("--out", default="ranked.json")
    sp.set_defaults(fn=rank)

    sp = sub.add_parser("verify", help="open each ad, read the plate, check APK and recall at RDW")
    sp.add_argument("input", nargs="?", default="ranked.json")
    sp.add_argument("--limit", type=int, default=400, help="ads to open, cheapest per APK month first (~1.5 s each)")
    sp.add_argument("--include-small", action="store_true")
    sp.add_argument("--out", default="verified.json")
    sp.set_defaults(fn=verify)

    sp = sub.add_parser("report", help="rank verified cars by price per month of RDW APK")
    sp.add_argument("input", nargs="?", default="verified.json")
    sp.add_argument("--min-months", type=float, default=7)
    sp.add_argument("--top", type=int, default=60)
    sp.add_argument("--ad-apk", action="store_true", help="fall back to the APK stated in the ad when RDW has no date")
    sp.add_argument("--out", default="final.json")
    sp.set_defaults(fn=report)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
