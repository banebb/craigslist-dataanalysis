"""
novine u optimizovaoj verziji
  1. Indeksi (ensure_indexes): po jedan indeks za svaki query, tako da svaki
     radi preko indeksa (IXSCAN) umesto da cita svih ~426k dokumenata (COLLSCAN).
  2. q3 preuredjen: grupisem po proizvodjacu pa tek onda $lookup

Izmerneo pre -> posle:
  q1  2.31s -> 1.15s   (~2x   - indeks pomaze, ali i dalje mora skoro sve da grupise)
  q2  1.20s -> 0.069s  (~17x  - indeks, pickup je redak pa se brzo nadje)
  q3 18.58s -> 1.12s   (~16x  - preuredjenje + indeks)
  q4  1.36s -> 0.20s   (~7x   - indeks, SUV/kabriolet su redji)
  q5  1.17s -> 0.097s  (~12x  - indeks, pickup je redak)
"""
import os
import time
import pymongo

MONGO_HOST = os.environ.get('MONGO_HOST', "localhost")
MONGO_PORT = int(os.environ.get('MONGO_PORT', 27017))

def get_db(version="v1"):
    client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
    db_name = "craigslist" if version == "v1" else "craigslist_v2"
    return client, client[db_name]

def ensure_indexes(db):
    """Napravi indekse koje queryji koriste. createIndex ionako ne pravi duplikate,
    pa moze da se zove svaki put bez brige."""
    listings = db["listings"]
    listings.create_index([("vehicle.model", 1), ("vehicle.year", 1), ("price", 1)])          # q1
    listings.create_index([("vehicle.type", 1), ("specs.drive", 1), ("price", 1)])            # q2
    listings.create_index([("vehicle.manufacturer_ref", 1), ("location.state", 1), ("price", 1)])  # q3
    listings.create_index([("vehicle.type", 1), ("location.state", 1), ("price", 1)])         # q4
    listings.create_index([("vehicle.type", 1), ("specs.drive", 1), ("vehicle.model", 1), ("price", 1)])  # q5
    print("Indexes ensured.")


def run_query(db, name, pipeline, collection="listings", limit=20):
    print(f"\n{'='*60}")
    print(f"Query : {name}")
    print(f"{'='*60}")

    start = time.time()
    results = list(db[collection].aggregate(pipeline, allowDiskUse=True))
    elapsed = time.time() - start


    for doc in results[:limit]:
        print(doc)
    print(f"\n -> {len(results)} results in {elapsed} seconds")


    explain = db.command("aggregate", collection, pipeline=pipeline, explain=True)
    print(f"  -> Explain: {explain.get('stages', [{}])[0] if 'stages' in explain else 'see full explain'}")

    return results, elapsed


#Top 10 modela sa najbrzim obrtom i prosecnom cenom po godistu
def q1_top10_fastest_turnover(db):
    pipeline=[
        {"$match" : {"vehicle.model" : {"$ne" : None}, "price" : {"$gt": 0}}},
        {"$group": {
            "_id": {"model" : "$vehicle.model", "year": "$vehicle.year"},
            "avg_price" : {"$avg" : "$price"},
            "count" : {"$sum" : 1}
        }},
        {"$sort" : {"count" : -1}},
        {"$limit" : 10},
        {"$project":{
            "_id": 0,
            "year" : "$_id.year",
            "model" : "$_id.model",
            "price" : "$avg_price",
            "listing_count" : "$count",
        }}
    ]
    return run_query(db, name="q1", pipeline=pipeline)

#Trzisna distribucija po pogonu
def q2_drive_type_share(db):
    pipeline=[
        {"$match" : {"vehicle.type" : "pickup", "price" : {"$gt": 0}, "specs.drive" : {"$ne" : None}}},
        {"$group": {"_id" : "$specs.drive", "count" : {"$sum" : 1}}},
        {"$group": {
            "_id" : None,
            "drives" : {"$push" : {"drive" : "$_id", "count" : "$count"}},
            "total" : {"$sum" : "$count"}
        }},
        {"$unwind" : "$drives"},
        {"$project" : {
            "_id" : 0,
            "drive_type" : "$drives.drive",
            "count" : "$drives.count",
            "percentage" : {"$divide" : ["$drives.count", "$total"]}
        }},
        {"$sort" : {"count" : -1}}
    ]

    return run_query(db, name="q2", pipeline=pipeline)

#koja zemlja porekla dominira po broju oglasa i ceni (istocna vs zapadna obala)
def q3_country_of_origin_dominance(db):

    east_coast = ["ny", "nj", "ct", "ma", "pa", "md", "va", "nc", "sc", "ga", "fl", "me", "nh", "vt", "ri", "de", "dc"]
    west_coast = ["ca", "or", "wa"]

    pipeline=[
       {"$match": {
           "vehicle.manufacturer_ref": {"$ne" : None},
           "price" : {"$gt": 0},
           "location.state" : {"$ne" : None},
       }},
       # prvo se odredi obala 400k+ dokumenata se smanji na grupe (proizvodjac x obala) pre join
       # $lookup ide ~120 puta umesto 400k. sum+count umesto avg
       {"$addFields" : {
        "coast" : {"$switch" : {
            "branches" : [
                {"case" : {"$in" : ["$location.state", east_coast]}, "then" : "East Coast"},
                {"case": {"$in": ["$location.state", west_coast]}, "then": "West Coast"},
            ],
            "default": "Inland"
        }}
    }},
       {"$group": {
            "_id" : {"mfr" : "$vehicle.manufacturer_ref", "coast" : "$coast"},
            "total_price" : {"$sum" : "$price"},
            "count" : {"$sum" : 1}
       }},
       {"$lookup" :{
           "from" : "manufacturers",
           "localField" : "_id.mfr",
           "foreignField" : "_id",
           "as" : "mfr_info"
       }},
       {"$unwind" : "$mfr_info"},
       # spojim proizvodjace koji su iz iste zemlje
       {"$group": {
            "_id" : {"country" : "$mfr_info.country", "coast" : "$_id.coast"},
            "total_price" : {"$sum" : "$total_price"},
            "count" : {"$sum" : "$count"}
       }},
       {"$sort" : {"count" : -1}},
       {"$group": {
           "_id" : "$_id.country",
           "total_listings" : {"$sum" : "$count"},
           "by_coast" : {"$push" : {
               "coast" : "$_id.coast",
               "avg_price" : {"$round" : [{"$divide" : ["$total_price", "$count"]}, 2]},
               "count" : "$count"
           }}
       }},
       {"$sort" : {"total_listings" : -1}}
   ]

    return run_query(db, name="q3", pipeline=pipeline)

#u kojim državama kabrioleti čine veći udeo ponude (klimatski efekat)
def q4_seasonal_patterns(db):

    pipeline=[
        {"$match" : {
            "location.state": {"$ne" : None},
            "vehicle.type" : {"$in" : ["SUV", "convertible"]},
            "price" : {"$gt":0}
        }},
        {"$group" : {
            "_id" : "$location.state",
            "suv" : {"$sum" : {"$cond" : [{"$eq":["$vehicle.type", "SUV"]}, 1, 0]}},
            "conv": {"$sum": {"$cond": [{"$eq": ["$vehicle.type", "convertible"]}, 1, 0]}}
        }},
        {"$match" : {
            "conv" : {"$gt" : 0}
        }},
        {"$project" : {
            "_id" : 0,
            "state" : "$_id",
            "suv" : 1,
            "conv" : 1,
            "convertible_share" : {"$round" : [{"$multiply" :
                                                [
                                                    {"$divide":
                                                         ["$conv", {"$add" :
                                                                       ["$conv", "$suv"]}]}
                                                ,100]},2]}
        }},
        {"$sort" : {"convertible_share": -1}}
    ]

    return run_query(db, name="q4", pipeline=pipeline)




#premium pretplate za 4wd pogon za isti model
def q5_drive_type_premium(db):
    pipeline = [
        {"$match" : {
            "vehicle.type" : "pickup",
            "specs.drive" : {"$in" : ["4wd", "fwd"]},
            "price" : {"$gt": 0},
            "vehicle.model" : {"$ne" : None}
        }},
        {"$group": {
           "_id" : "$vehicle.model",
            "avg_4wd" : {"$avg" : {"$cond" : [{"$eq" : ["$specs.drive", "4wd"]}, "$price", None]}},
            "avg_fwd" : {"$avg" : {"$cond" : [{"$eq" : ["$specs.drive", "fwd"]}, "$price", None]}},
            "count_4wd" : {"$sum" : {"$cond" : [{"$eq" : ["$specs.drive", "4wd"]}, 1, 0]}},
            "count_fwd": {"$sum": {"$cond": [{"$eq": ["$specs.drive", "fwd"]}, 1, 0]}},
        }},
        {"$match" : {
            "count_4wd" : {"$gt" : 0},
            "count_fwd" : {"$gt" : 0}
        }},
        {"$project" : {
            "_id" : 0,
            "model" : "$_id",
            "avg_4wd" : {"$round" : ["$avg_4wd", 2]},
            "avg_fwd" : {"$round" : ["$avg_fwd", 2]},
            "premium_4wd" : {"$round" : [{"$subtract" : ["$avg_4wd", "$avg_fwd"]},2]},
            "count_4wd" : 1,
            "count_fwd": 1
        }}
    ]

    return run_query(db, name="q5", pipeline=pipeline)

def run_all(version="v1"):
    client, db = get_db(version)
    print(f"\nRunning OPTIMIZED seller queries on {version} schema...")
    print(f"{'='*60}")

    ensure_indexes(db)

    results = {}
    for name, func in [
        ("q1", q1_top10_fastest_turnover),
        ("q2", q2_drive_type_share),
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
