# Seller Queries — Regular vs Optimized

Each of the five seller-role questions below is shown twice as **complete,
standalone code**: a **normal** version (no index, collection scan) and an
**optimized** version (creates its own index inline, then runs). Every block can
be copied into a `.py` file and run on its own.

## Setup & methodology

- **Database:** MongoDB 7.0, `craigslist` schema (v1)
- **Data:** `listings` — 426,880 documents; `manufacturers` — 42 documents
- **Timing:** median of 3 runs after one warm-up run, `allowDiskUse=True`
- **normal** = query with **no custom index** (collection scan / `COLLSCAN`)
- **optimized** = query with its supporting index in place (`IXSCAN`); q3 also
  restructures the pipeline (group by manufacturer *before* the `$lookup`).

| Query | Question | Normal | Optimized | Speed-up |
|-------|----------|-------:|----------:|---------:|
| q1 | Top 10 models by turnover, avg price per year | 2.3231 s | 1.1745 s | **2.0×** |
| q2 | Market share by drive type (pickups) | 1.2098 s | 0.0720 s | **16.8×** |
| q3 | Country-of-origin dominance, East vs West coast | 18.3846 s | 1.1743 s | **15.7×** |
| q4 | States where convertibles hold a bigger share | 1.2932 s | 0.2058 s | **6.3×** |
| q5 | 4WD price premium per model (pickups) | 1.1179 s | 0.1111 s | **10.1×** |

---

## q1 — Top 10 modela sa najbržim obrtom i prosečnom cenom po godištu

*Top 10 models by listing turnover with average price per model-year.*

### Normal (no index)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]

pipeline = [
    {"$match": {"vehicle.model": {"$ne": None}, "price": {"$gt": 0}}},
    {"$group": {
        "_id": {"model": "$vehicle.model", "year": "$vehicle.year"},
        "avg_price": {"$avg": "$price"},
        "count": {"$sum": 1}
    }},
    {"$sort": {"count": -1}},
    {"$limit": 10},
    {"$project": {
        "_id": 0,
        "year": "$_id.year",
        "model": "$_id.model",
        "price": "$avg_price",
        "listing_count": "$count",
    }}
]

start = time.time()
results = list(db["listings"].aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

### Optimized (index built inline)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]
listings = db["listings"]

# index for this query — filter + group served by IXSCAN instead of COLLSCAN
listings.create_index([("vehicle.model", 1), ("vehicle.year", 1), ("price", 1)])

pipeline = [
    {"$match": {"vehicle.model": {"$ne": None}, "price": {"$gt": 0}}},
    {"$group": {
        "_id": {"model": "$vehicle.model", "year": "$vehicle.year"},
        "avg_price": {"$avg": "$price"},
        "count": {"$sum": 1}
    }},
    {"$sort": {"count": -1}},
    {"$limit": 10},
    {"$project": {
        "_id": 0,
        "year": "$_id.year",
        "model": "$_id.model",
        "price": "$avg_price",
        "listing_count": "$count",
    }}
]

start = time.time()
results = list(listings.aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

**Timing:** 2.3231 s → 1.1745 s — **~2.0× faster**. Smallest gain: almost every
document has a model and positive price, so the query still groups nearly the
whole collection even with the index.

---

## q2 — Tržišna distribucija po pogonu

*Market share of each drive type among pickups.*

### Normal (no index)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]

pipeline = [
    {"$match": {"vehicle.type": "pickup", "price": {"$gt": 0}, "specs.drive": {"$ne": None}}},
    {"$group": {"_id": "$specs.drive", "count": {"$sum": 1}}},
    {"$group": {
        "_id": None,
        "drives": {"$push": {"drive": "$_id", "count": "$count"}},
        "total": {"$sum": "$count"}
    }},
    {"$unwind": "$drives"},
    {"$project": {
        "_id": 0,
        "drive_type": "$drives.drive",
        "count": "$drives.count",
        "percentage": {"$divide": ["$drives.count", "$total"]}
    }},
    {"$sort": {"count": -1}}
]

start = time.time()
results = list(db["listings"].aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

### Optimized (index built inline)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]
listings = db["listings"]

# index for this query — the rare "pickup" slice is found via IXSCAN
listings.create_index([("vehicle.type", 1), ("specs.drive", 1), ("price", 1)])

pipeline = [
    {"$match": {"vehicle.type": "pickup", "price": {"$gt": 0}, "specs.drive": {"$ne": None}}},
    {"$group": {"_id": "$specs.drive", "count": {"$sum": 1}}},
    {"$group": {
        "_id": None,
        "drives": {"$push": {"drive": "$_id", "count": "$count"}},
        "total": {"$sum": "$count"}
    }},
    {"$unwind": "$drives"},
    {"$project": {
        "_id": 0,
        "drive_type": "$drives.drive",
        "count": "$drives.count",
        "percentage": {"$divide": ["$drives.count", "$total"]}
    }},
    {"$sort": {"count": -1}}
]

start = time.time()
results = list(listings.aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

**Timing:** 1.2098 s → 0.0720 s — **~16.8× faster**. Pickups are a small slice, so
the index prunes most of the collection up front.

---

## q3 — Koja zemlja porekla dominira po broju oglasa i ceni (istočna vs zapadna obala)

*Which country of origin dominates by listing count and price, East vs West coast.*

### Normal (no index — joins first, then groups)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]

east_coast = ["ny", "nj", "ct", "ma", "pa", "md", "va", "nc", "sc", "ga",
              "fl", "me", "nh", "vt", "ri", "de", "dc"]
west_coast = ["ca", "or", "wa"]

pipeline = [
    {"$match": {
        "vehicle.manufacturer_ref": {"$ne": None},
        "price": {"$gt": 0},
        "location.state": {"$ne": None},
    }},
    {"$lookup": {
        "from": "manufacturers",
        "localField": "vehicle.manufacturer_ref",
        "foreignField": "_id",
        "as": "mfr_info"
    }},
    {"$unwind": "$mfr_info"},
    {"$addFields": {
        "coast": {"$switch": {
            "branches": [
                {"case": {"$in": ["$location.state", east_coast]}, "then": "East Coast"},
                {"case": {"$in": ["$location.state", west_coast]}, "then": "West Coast"},
            ],
            "default": "Inland"
        }}
    }},
    {"$group": {
        "_id": {"country": "$mfr_info.country", "coast": "$coast"},
        "avg_price": {"$avg": "$price"},
        "count": {"$sum": 1}
    }},
    {"$sort": {"count": -1}},
    {"$group": {
        "_id": "$_id.country",
        "total_listings": {"$sum": "$count"},
        "by_coast": {"$push": {
            "coast": "$_id.coast",
            "avg_price": {"$round": ["$avg_price", 2]},
            "count": "$count"
        }}
    }},
    {"$sort": {"total_listings": -1}}
]

start = time.time()
results = list(db["listings"].aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

### Optimized (index inline + group before `$lookup`)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]
listings = db["listings"]

# index for this query
listings.create_index([("vehicle.manufacturer_ref", 1), ("location.state", 1), ("price", 1)])

east_coast = ["ny", "nj", "ct", "ma", "pa", "md", "va", "nc", "sc", "ga",
              "fl", "me", "nh", "vt", "ri", "de", "dc"]
west_coast = ["ca", "or", "wa"]

pipeline = [
    {"$match": {
        "vehicle.manufacturer_ref": {"$ne": None},
        "price": {"$gt": 0},
        "location.state": {"$ne": None},
    }},
    # assign coast, then collapse 400k+ docs into (manufacturer × coast) groups BEFORE the join
    {"$addFields": {
        "coast": {"$switch": {
            "branches": [
                {"case": {"$in": ["$location.state", east_coast]}, "then": "East Coast"},
                {"case": {"$in": ["$location.state", west_coast]}, "then": "West Coast"},
            ],
            "default": "Inland"
        }}
    }},
    {"$group": {
        "_id": {"mfr": "$vehicle.manufacturer_ref", "coast": "$coast"},
        "total_price": {"$sum": "$price"},
        "count": {"$sum": 1}
    }},
    {"$lookup": {
        "from": "manufacturers",
        "localField": "_id.mfr",
        "foreignField": "_id",
        "as": "mfr_info"
    }},
    {"$unwind": "$mfr_info"},
    # merge manufacturers from the same country
    {"$group": {
        "_id": {"country": "$mfr_info.country", "coast": "$_id.coast"},
        "total_price": {"$sum": "$total_price"},
        "count": {"$sum": "$count"}
    }},
    {"$sort": {"count": -1}},
    {"$group": {
        "_id": "$_id.country",
        "total_listings": {"$sum": "$count"},
        "by_coast": {"$push": {
            "coast": "$_id.coast",
            "avg_price": {"$round": [{"$divide": ["$total_price", "$count"]}, 2]},
            "count": "$count"
        }}
    }},
    {"$sort": {"total_listings": -1}}
]

start = time.time()
results = list(listings.aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

**Timing:** 18.3846 s → 1.1743 s — **~15.7× faster**. Biggest absolute win: moving
the `$lookup` after the group cuts the join from ~400k calls down to ~120.

---

## q4 — U kojim državama kabrioleti čine veći udeo ponude (klimatski efekat)

*In which states convertibles make up a larger share of supply (climate effect).*

### Normal (no index)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]

pipeline = [
    {"$match": {
        "location.state": {"$ne": None},
        "vehicle.type": {"$in": ["SUV", "convertible"]},
        "price": {"$gt": 0}
    }},
    {"$group": {
        "_id": "$location.state",
        "suv": {"$sum": {"$cond": [{"$eq": ["$vehicle.type", "SUV"]}, 1, 0]}},
        "conv": {"$sum": {"$cond": [{"$eq": ["$vehicle.type", "convertible"]}, 1, 0]}}
    }},
    {"$match": {"conv": {"$gt": 0}}},
    {"$project": {
        "_id": 0,
        "state": "$_id",
        "suv": 1,
        "conv": 1,
        "convertible_share": {"$round": [{"$multiply": [
            {"$divide": ["$conv", {"$add": ["$conv", "$suv"]}]}, 100]}, 2]}
    }},
    {"$sort": {"convertible_share": -1}}
]

start = time.time()
results = list(db["listings"].aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

### Optimized (index built inline)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]
listings = db["listings"]

# index for this query — the SUV/convertible filter is served by IXSCAN
listings.create_index([("vehicle.type", 1), ("location.state", 1), ("price", 1)])

pipeline = [
    {"$match": {
        "location.state": {"$ne": None},
        "vehicle.type": {"$in": ["SUV", "convertible"]},
        "price": {"$gt": 0}
    }},
    {"$group": {
        "_id": "$location.state",
        "suv": {"$sum": {"$cond": [{"$eq": ["$vehicle.type", "SUV"]}, 1, 0]}},
        "conv": {"$sum": {"$cond": [{"$eq": ["$vehicle.type", "convertible"]}, 1, 0]}}
    }},
    {"$match": {"conv": {"$gt": 0}}},
    {"$project": {
        "_id": 0,
        "state": "$_id",
        "suv": 1,
        "conv": 1,
        "convertible_share": {"$round": [{"$multiply": [
            {"$divide": ["$conv", {"$add": ["$conv", "$suv"]}]}, 100]}, 2]}
    }},
    {"$sort": {"convertible_share": -1}}
]

start = time.time()
results = list(listings.aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

**Timing:** 1.2932 s → 0.2058 s — **~6.3× faster**. SUV/convertible are a modest
fraction of the data, so the index skips most documents.

---

## q5 — Premium za 4WD pogon za isti model

*Price premium of 4WD over FWD for the same model (pickups).*

### Normal (no index)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]

pipeline = [
    {"$match": {
        "vehicle.type": "pickup",
        "specs.drive": {"$in": ["4wd", "fwd"]},
        "price": {"$gt": 0},
        "vehicle.model": {"$ne": None}
    }},
    {"$group": {
        "_id": "$vehicle.model",
        "avg_4wd": {"$avg": {"$cond": [{"$eq": ["$specs.drive", "4wd"]}, "$price", None]}},
        "avg_fwd": {"$avg": {"$cond": [{"$eq": ["$specs.drive", "fwd"]}, "$price", None]}},
        "count_4wd": {"$sum": {"$cond": [{"$eq": ["$specs.drive", "4wd"]}, 1, 0]}},
        "count_fwd": {"$sum": {"$cond": [{"$eq": ["$specs.drive", "fwd"]}, 1, 0]}},
    }},
    {"$match": {"count_4wd": {"$gt": 0}, "count_fwd": {"$gt": 0}}},
    {"$project": {
        "_id": 0,
        "model": "$_id",
        "avg_4wd": {"$round": ["$avg_4wd", 2]},
        "avg_fwd": {"$round": ["$avg_fwd", 2]},
        "premium_4wd": {"$round": [{"$subtract": ["$avg_4wd", "$avg_fwd"]}, 2]},
        "count_4wd": 1,
        "count_fwd": 1
    }}
]

start = time.time()
results = list(db["listings"].aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

### Optimized (index built inline)

```python
import time
import pymongo

client = pymongo.MongoClient("localhost", 27017)
db = client["craigslist"]
listings = db["listings"]

# index for this query — pickup + drive filter covered by IXSCAN
listings.create_index([("vehicle.type", 1), ("specs.drive", 1), ("vehicle.model", 1), ("price", 1)])

pipeline = [
    {"$match": {
        "vehicle.type": "pickup",
        "specs.drive": {"$in": ["4wd", "fwd"]},
        "price": {"$gt": 0},
        "vehicle.model": {"$ne": None}
    }},
    {"$group": {
        "_id": "$vehicle.model",
        "avg_4wd": {"$avg": {"$cond": [{"$eq": ["$specs.drive", "4wd"]}, "$price", None]}},
        "avg_fwd": {"$avg": {"$cond": [{"$eq": ["$specs.drive", "fwd"]}, "$price", None]}},
        "count_4wd": {"$sum": {"$cond": [{"$eq": ["$specs.drive", "4wd"]}, 1, 0]}},
        "count_fwd": {"$sum": {"$cond": [{"$eq": ["$specs.drive", "fwd"]}, 1, 0]}},
    }},
    {"$match": {"count_4wd": {"$gt": 0}, "count_fwd": {"$gt": 0}}},
    {"$project": {
        "_id": 0,
        "model": "$_id",
        "avg_4wd": {"$round": ["$avg_4wd", 2]},
        "avg_fwd": {"$round": ["$avg_fwd", 2]},
        "premium_4wd": {"$round": [{"$subtract": ["$avg_4wd", "$avg_fwd"]}, 2]},
        "count_4wd": 1,
        "count_fwd": 1
    }}
]

start = time.time()
results = list(listings.aggregate(pipeline, allowDiskUse=True))
elapsed = time.time() - start

for doc in results:
    print(doc)
print(f"\n-> {len(results)} results in {elapsed:.4f} seconds")
client.close()
```

**Timing:** 1.1179 s → 0.1111 s — **~10.1× faster**. As in q2, pickups are rare so
the index prunes most of the collection immediately.
