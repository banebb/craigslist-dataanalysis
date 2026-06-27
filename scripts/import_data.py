import os
import math
import pymongo
import pandas as pd
from datetime import datetime

MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))
MONGO_DB = os.environ.get("MONGO_DB", "craigslist")
CSV_PATH = os.environ.get("CSV_PATH", "/app/data/craigslist_vehicles.csv")

MANUFACTURER_COUNTRIES = {
    "ford": "USA", "chevrolet": "USA", "toyota": "Japan", "honda": "Japan",
    "nissan": "Japan", "jeep": "USA", "ram": "USA", "gmc": "USA",
    "bmw": "Germany", "mercedes-benz": "Germany", "dodge": "USA",
    "hyundai": "South Korea", "subaru": "Japan", "kia": "South Korea",
    "volkswagen": "Germany", "chrysler": "USA", "lexus": "Japan",
    "mazda": "Japan", "audi": "Germany", "cadillac": "USA",
    "acura": "Japan", "buick": "USA", "infiniti": "Japan",
    "lincoln": "USA", "volvo": "Sweden", "mitsubishi": "Japan",
    "pontiac": "USA", "mini": "UK", "land rover": "UK",
    "mercury": "USA", "jaguar": "UK", "porsche": "Germany",
    "fiat": "Italy", "saturn": "USA", "alfa-romeo": "Italy",
    "tesla": "USA", "datsun": "Japan", "harley-davidson": "USA",
    "rover": "UK", "ferrari": "Italy", "aston-martin": "UK",
    "hennessey": "USA", "morgan": "UK",
}

CHUNK_SIZE = 50_000


def clean_value(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return val


def build_listing(row):
    lat = clean_value(row.get("lat"))
    long = clean_value(row.get("long"))
    geo = None
    if lat is not None and long is not None:
        geo = {"type": "Point", "coordinates": [float(long), float(lat)]}

    posting_date = clean_value(row.get("posting_date"))
    if posting_date and isinstance(posting_date, str):
        try:
            posting_date = datetime.fromisoformat(posting_date.replace("T", " ").rstrip("Z"))
        except ValueError:
            posting_date = None

    odometer = clean_value(row.get("odometer"))
    if odometer is not None:
        try:
            odometer = float(odometer)
        except (ValueError, TypeError):
            odometer = None

    price = clean_value(row.get("price"))
    if price is not None:
        try:
            price = int(float(price))
        except (ValueError, TypeError):
            price = None

    year = clean_value(row.get("year"))
    if year is not None:
        try:
            year = int(float(year))
        except (ValueError, TypeError):
            year = None

    return {
        "_id": int(row["id"]),
        "url": clean_value(row.get("url")),
        "price": price,
        "posting_date": posting_date,
        "vehicle": {
            "year": year,
            "manufacturer_ref": clean_value(row.get("manufacturer")),
            "model": clean_value(row.get("model")),
            "vin": clean_value(row.get("VIN")),
            "type": clean_value(row.get("type")),
            "size": clean_value(row.get("size")),
            "paint_color": clean_value(row.get("paint_color")),
        },
        "specs": {
            "condition": clean_value(row.get("condition")),
            "cylinders": clean_value(row.get("cylinders")),
            "fuel": clean_value(row.get("fuel")),
            "odometer_miles": odometer,
            "transmission": clean_value(row.get("transmission")),
            "drive": clean_value(row.get("drive")),
            "title_status": clean_value(row.get("title_status")),
        },
        "location": {
            "region_ref": clean_value(row.get("region")),
            "state": clean_value(row.get("state")),
            "county": clean_value(row.get("county")),
            "geo": geo,
        },
        "media": {
            "image_url": clean_value(row.get("image_url")),
            "description": clean_value(row.get("description")),
        },
    }


def import_data():
    client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
    db = client[MONGO_DB]

    db.listings.drop()
    db.regions.drop()
    db.manufacturers.drop()

    print(f"Reading CSV: {CSV_PATH}")
    regions = {}
    manufacturers = {}
    total_inserted = 0

    for chunk in pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE, dtype=str):
        listings = []
        for _, row in chunk.iterrows():
            row_dict = row.to_dict()
            listing = build_listing(row_dict)
            listings.append(listing)

            region = clean_value(row_dict.get("region"))
            if region and region not in regions:
                regions[region] = {
                    "_id": region,
                    "url": clean_value(row_dict.get("region_url")),
                    "state": clean_value(row_dict.get("state")),
                    "listing_count": 0,
                }
            if region:
                regions[region]["listing_count"] += 1

            mfr = clean_value(row_dict.get("manufacturer"))
            if mfr and mfr not in manufacturers:
                manufacturers[mfr] = {
                    "_id": mfr,
                    "display_name": mfr.title(),
                    "country": MANUFACTURER_COUNTRIES.get(mfr, "Unknown"),
                    "listing_count": 0,
                }
            if mfr:
                manufacturers[mfr]["listing_count"] += 1

        if listings:
            db.listings.insert_many(listings, ordered=False)
            total_inserted += len(listings)
            print(f"  Inserted {total_inserted} listings...")

    if regions:
        db.regions.insert_many(list(regions.values()), ordered=False)
        print(f"Inserted {len(regions)} regions")

    if manufacturers:
        db.manufacturers.insert_many(list(manufacturers.values()), ordered=False)
        print(f"Inserted {len(manufacturers)} manufacturers")

    print(f"\nDone! Total: {total_inserted} listings, {len(regions)} regions, {len(manufacturers)} manufacturers")
    client.close()


if __name__ == "__main__":
    import_data()
