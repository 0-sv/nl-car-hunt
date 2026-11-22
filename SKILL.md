---
name: nl-car-hunt
description: Sweep every cheap used-car ad in the Netherlands (AutoScout24 + Marktplaats), rank by price per APK month, and check each shortlisted plate's APK and recalls at RDW. Use when someone wants a budget or banger car in NL, asks for cars with a long or "nieuwe" APK under a price, or wants a full sweep of a price range instead of a sample.
---

# NL car hunt

The unit of value is the **APK month**: one month of legal driving before the next inspection. A €900 car with 12 APK months (€75/month) beats a €600 car with 5 (€120/month). Rank everything on price per APK month.

`carhunt.py` sits in this skill's base directory. It is standard-library Python. Run every command from a scratch directory, because it writes its files to the current directory.

## Steps

1. **Settle the brief.** Read the budget, size floor, minimum APK months and fuel preference from the request. Defaults: max €1,500, min €300, no city cars, at least 7 APK months, petrol preferred for old cars (diesel road tax is high). Done when every flag below has a value.

2. **Sweep.** Start both scrapes in the background, in parallel:
   ```
   python3 carhunt.py scrape-as24 --max-price 1500
   python3 carhunt.py scrape-mp   --max-price 1500
   ```
   Each takes 5 to 10 minutes and ends with `N unique of M reported`. Done when both lines are printed and each covers at least 90% of its total. Tell the user both coverage numbers.

3. **Rank.** `python3 carhunt.py rank as24.jsonl mp.jsonl --max-price 1500`. This drops city cars, ads that say damage/export/parts/lease/no APK, and ads with no stated APK date. Done when it prints the count of ranked cars.

4. **Verify.** `python3 carhunt.py verify --limit 400` in the background (about 1.5 s per ad). It opens each ad, reads the plate, and gets the real APK expiry, recall and export status from RDW. It also reads the full description for sold, auction and issue phrases. Pass `--include-small` when small cars are in scope.
   If it prints `WARNING: RDW stopped answering`, check `dig opendata.rdw.nl`. The record has been missing for whole days. Continue with `report --ad-apk`, and label every APK date as unverified in the answer.

5. **Report.** `python3 carhunt.py report` prints the verified ranking and writes `final.json`. Then judge the shortlist yourself, car by car:
   - Read the `issues` hits in the `full` text. The match is a hint: "geen schade" and "schadevrij" mean no damage.
   - Check the engine against **Engines to flag** below.
   - Note an open recall (`rdw_recall` = `Ja`).

   Done when every shortlisted car has a clickable ad link, its APK date and source (RDW or ad), its price type, and a verdict on its issues and engine.

## The answer

- A table: car, year, km, price, APK date, APK months, city, link.
- Three picks: best value (lowest price per APK month), longest APK, and lowest risk (service history, one owner, belt already replaced).
- An avoid list with the reason for each car.
- Coverage: ads swept per site, ads verified at RDW.
- The caveats in **Reading the data**.

## Reading the data

- `ptype` `MIN_BID` is "bieden vanaf": a minimum bid, not the price. `FIXED` is an asking price.
- "Nieuwe APK" often means the seller does the APK at the sale. RDW then shows an expired date, and `report` drops the car as a short APK. The RDW date is the truth.
- Auctions ("proveiling", "bied mee") list a start price. `verify` marks them and `report` drops them.
- Ads are from the day of the sweep. Tell the user to confirm the car is still for sale before they drive out. The plate check at https://ovi.rdw.nl shows the same APK date for free.
- Gaspedaal and AutoTrack refuse automated fetches. They mostly mirror the dealer stock on AutoScout24, so the two sweeps cover the market.
- WebFetch summarises pages and strips link targets, and search engines do not index today's ads. Use the script, not those tools, to get ad URLs.

## Engines to flag

- VW group 1.4 TSI and 1.2 TSI, about 2006 to 2012 (Golf, Passat, Touran, Leon, Octavia): the timing chain stretches, and failure ends the car at this price.
- PSA/BMW 1.6 THP and 1.6 VTi "Prince" (Peugeot 207/308/3008, Citroën C4/DS, Mini): the timing chain and oil consumption.
- Hybrids (Prius, Civic IMA) at this age: the traction battery is near its end, and a new one costs more than the car.
- High-mileage diesels: road tax (MRB) is several times the petrol rate, so they cost more per APK month than the price suggests.

Simple old petrol engines last longest per euro: Mazda 1.8/2.0, Ford 1.6 Zetec/Duratec, Toyota 1.4/1.6 VVT-i, Volvo/Ford 1.8, Nissan 1.6/1.8, Opel 1.6 8V/16V, Peugeot TU/EW engines.
