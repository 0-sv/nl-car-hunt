# nl-car-hunt

Find the cheapest used car in the Netherlands per month of APK left, and check every APK date at the RDW.

It sweeps every ad in a price range on AutoScout24 and Marktplaats, not just the first few pages. It ranks the cars on price per month of APK. Then it opens each ad, reads the number plate, and asks RDW open data for the real APK expiry date and open recalls.

Three rows from a sweep of everything up to €1,500 in November 2026 (about 16,000 ads):

```
€/mo  price  type apk        src  year  km       model                      city
  58    650 FIX 2027-10-20 RDW   2000   254736 FORD FOCUS                 Boekel
  59   1100 MIN 2028-05-27 RDW   1993          AUTO UNION AUDI 80 AVANT   Sint-Oedenrode
  68    799 FIX 2027-11-06 RDW   2007   348261 MAZDA MAZDA 6              Oosterwolde
```

## Why price per APK month

A car bought to drive until it dies is worth the legal driving it has left. A €900 car with 12 months of APK costs €75 a month. A €600 car with 5 months costs €120 a month, and then it needs a new inspection that it may not pass. Many ads say "nieuwe APK" when the seller only means "at the sale", so the tool trusts the RDW date, not the ad.

## Install

As a Claude Code skill:

```sh
git clone https://github.com/0-sv/nl-car-hunt ~/.claude/skills/nl-car-hunt
```

Then ask Claude something like "find me a car under €1500 with a long APK, not a tiny one". The skill runs the steps below and gives you a shortlist with links.

As a plain script, you need only Python 3.9 or later. There are no dependencies.

## Usage

Run each step in a scratch directory. Each step writes its output there.

```
python3 carhunt.py scrape-as24 --max-price 1500      # all AutoScout24 ads, 5 to 10 min
python3 carhunt.py scrape-mp   --max-price 1500      # all Marktplaats ads, 5 to 10 min
python3 carhunt.py rank as24.jsonl mp.jsonl          # filter, read the APK from the ad text
python3 carhunt.py verify --limit 400                # plate + RDW check, about 1.5 s per ad
python3 carhunt.py report                            # final ranking
```

Run `python3 carhunt.py <step> --help` to see the options for each step. The most useful options:

- `--max-price` and `--min-price`
- `--min-months`, the minimum months of APK left
- `--include-small`, to keep city cars
- `report --ad-apk`, which uses the APK date from the ad when RDW does not answer

## How it gets everything

- AutoScout24 serves at most 400 results per search. The tool splits the price range until each slice fits, and splits by year when hundreds of cars share one price, such as €1,500.
- The Marktplaats API serves at most 5,000 results per search. Ads with the same price move between pages while the tool reads them, so one sort order misses about 10%. A second pass sorted by date fills most of that gap.
- Gaspedaal and AutoTrack block automated requests. They mostly show the same dealer stock as AutoScout24.

## Notes

- This is for personal use. It waits 0.4 s between requests. The sites can change their pages at any time and break it.
- RDW open data has CC-0 terms. If `opendata.rdw.nl` does not answer, `verify` stops asking and tells you so. You can check a single plate by hand at [ovi.rdw.nl](https://ovi.rdw.nl).
- "MIN" in the type column means "bieden vanaf": a minimum bid, not a fixed price.
