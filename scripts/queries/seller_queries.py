import os
import time
import pymongo

MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))


def get_db(version="v1"):
    client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
    db_name = "craigslist" if version == "v1" else "craigslist_v2"
    return client, client[db_name]


def run_query(db, name, pipeline, collection="listings"):
    print(f"\n{'='*60}")
    print(f"Query: {name}")
    print(f"{'='*60}")

    start = time.time()
    results = list(db[collection].aggregate(pipeline, allowDiskUse=True))
    elapsed = time.time() - start

    for doc in results[:10]:
        print(doc)
    print(f"\n  -> {len(results)} results in {elapsed:.3f}s")

    explain = db.command("aggregate", collection, pipeline=pipeline, explain=True)
    print(f"  -> Explain: {explain.get('stages', [{}])[0] if 'stages' in explain else 'see full explain'}")

    return results, elapsed


def q1_top10_fastest_turnover(db):
    """Top 10 modela sa najbržim obrtom i prosečnom cenom po godištu"""
    pipeline = [
        {"$match": {"vehicle.model": {"$ne": None}, "price": {"$gt": 0}}},
        {"$group": {
            "_id": {"model": "$vehicle.model", "year": "$vehicle.year"},
            "avg_price": {"$avg": "$price"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
        {"$project": {
            "model": "$_id.model",
            "year": "$_id.year",
            "avg_price": {"$round": ["$avg_price", 2]},
            "listing_count": "$count",
            "_id": 0,
        }},
    ]
    return run_query(db, "Q1: Top 10 modela - najbrži obrt i prosečna cena po godištu", pipeline)


def q2_arbitrage_opportunities(db):
    """U kojim državama je model precenjen/potcenjen - prilike za arbitražu"""
    pipeline = [
        {"$match": {"vehicle.model": {"$ne": None}, "price": {"$gt": 0}, "location.state": {"$ne": None}}},
        {"$group": {
            "_id": {"model": "$vehicle.model", "state": "$location.state"},
            "avg_price": {"$avg": "$price"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gte": 5}}},
        {"$group": {
            "_id": "$_id.model",
            "national_avg": {"$avg": "$avg_price"},
            "states": {"$push": {
                "state": "$_id.state",
                "avg_price": "$avg_price",
                "count": "$count",
            }},
        }},
        {"$unwind": "$states"},
        {"$addFields": {
            "states.price_diff_pct": {
                "$round": [{"$multiply": [
                    {"$divide": [{"$subtract": ["$states.avg_price", "$national_avg"]}, "$national_avg"]},
                    100
                ]}, 1]
            }
        }},
        {"$sort": {"states.price_diff_pct": -1}},
        {"$group": {
            "_id": "$_id",
            "national_avg": {"$first": "$national_avg"},
            "most_overpriced": {"$first": "$states"},
            "most_underpriced": {"$last": "$states"},
        }},
        {"$sort": {"national_avg": -1}},
        {"$limit": 10},
    ]
    return run_query(db, "Q2: Arbitražne prilike po državama", pipeline)


def q3_country_of_origin_dominance(db):
    """Koja zemlja porekla dominira po broju oglasa i ceni (istočna vs zapadna obala)"""
    east_coast = ["ny", "nj", "ct", "ma", "pa", "md", "va", "nc", "sc", "ga", "fl", "me", "nh", "vt", "ri", "de", "dc"]
    west_coast = ["ca", "or", "wa"]

    pipeline = [
        {"$match": {"vehicle.manufacturer_ref": {"$ne": None}, "price": {"$gt": 0}, "location.state": {"$ne": None}}},
        {"$lookup": {
            "from": "manufacturers",
            "localField": "vehicle.manufacturer_ref",
            "foreignField": "_id",
            "as": "mfr_info",
        }},
        {"$unwind": "$mfr_info"},
        {"$addFields": {
            "coast": {"$switch": {
                "branches": [
                    {"case": {"$in": ["$location.state", east_coast]}, "then": "East Coast"},
                    {"case": {"$in": ["$location.state", west_coast]}, "then": "West Coast"},
                ],
                "default": "Inland",
            }}
        }},
        {"$group": {
            "_id": {"country": "$mfr_info.country", "coast": "$coast"},
            "avg_price": {"$avg": "$price"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
        {"$group": {
            "_id": "$_id.country",
            "total_listings": {"$sum": "$count"},
            "by_coast": {"$push": {
                "coast": "$_id.coast",
                "avg_price": {"$round": ["$avg_price", 2]},
                "count": "$count",
            }},
        }},
        {"$sort": {"total_listings": -1}},
    ]
    return run_query(db, "Q3: Dominacija po zemlji porekla - istočna vs zapadna obala", pipeline)


def q4_seasonal_patterns(db):
    """Sezonska komponenta - kada se oglašavaju SUV-ovi vs kabrioleti"""
    pipeline = [
        {"$match": {
            "posting_date": {"$ne": None},
            "vehicle.type": {"$in": ["SUV", "convertible"]},
        }},
        {"$group": {
            "_id": {
                "month": {"$month": "$posting_date"},
                "type": "$vehicle.type",
            },
            "count": {"$sum": 1},
            "avg_price": {"$avg": "$price"},
        }},
        {"$sort": {"_id.month": 1}},
        {"$group": {
            "_id": "$_id.type",
            "monthly_data": {"$push": {
                "month": "$_id.month",
                "count": "$count",
                "avg_price": {"$round": ["$avg_price", 2]},
            }},
        }},
    ]
    return run_query(db, "Q4: Sezonski obrasci - SUV vs kabrioleti", pipeline)


def q5_drive_type_premium(db):
    """Tržišna distribucija po pogonu i premium za 4wd kod pickupa"""
    pipeline = [
        {"$match": {
            "vehicle.type": "pickup",
            "specs.drive": {"$ne": None},
            "price": {"$gt": 0},
        }},
        {"$group": {
            "_id": "$specs.drive",
            "avg_price": {"$avg": "$price"},
            "median_odometer": {"$avg": "$specs.odometer_miles"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"avg_price": -1}},
        {"$project": {
            "drive_type": "$_id",
            "avg_price": {"$round": ["$avg_price", 2]},
            "median_odometer": {"$round": ["$median_odometer", 0]},
            "count": 1,
            "_id": 0,
        }},
    ]
    return run_query(db, "Q5: Premium za 4WD kod pickup kamiona", pipeline)


def run_all(version="v1"):
    client, db = get_db(version)
    print(f"\nRunning seller queries on {version} schema...")
    print(f"{'='*60}")

    results = {}
    for name, func in [
        ("q1", q1_top10_fastest_turnover),
        ("q2", q2_arbitrage_opportunities),
        ("q3", q3_country_of_origin_dominance),
        ("q4", q4_seasonal_patterns),
        ("q5", q5_drive_type_premium),
    ]:
        results[name] = func(db)

    client.close()
    return results


if __name__ == "__main__":
    import sys
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    run_all(version)
