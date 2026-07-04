# Analiza tržišta polovnih vozila u SAD-u — Craigslist Vehicles

Projekat iz predmeta **Sistemi baza podataka (SBP)**.

**Autori:** Bane Božanić IN39/2022, Kosta Gaćina IN42/2022

---

## O datasetu

### Tema

Tržište polovnih automobila u SAD-u jedno je od najvećih maloprodajnih tržišta na svetu — preko 40 miliona vozila proda se godišnje. Craigslist je centralna peer-to-peer platforma na kojoj privatni prodavci i mali dileri postavljaju oglase.

### Skup podataka

Jedan veliki CSV fajl (`vehicles.csv`, 1.45 GB) sa 426.880 oglasa, od kojih svaki ima 26 raznovrsnih kolona koje pokrivaju identifikaciju, tehničke specifikacije, stanje, cenu, geografsku lokaciju i metapodatke.

### Zašto baš ovaj dataset

Kolone se prirodno grupišu u logičke celine, što ga čini izvanrednim kandidatom za document-oriented modelovanje gde svaki oglas postaje jedan ugneždeni MongoDB dokument.

### Tehničke informacije o datasetu

| Parametar | Vrednost |
|---|---|
| Veličina | 1.45 GB |
| Zapisa | 426.880 oglasa |
| Kolona | 26 |
| Godišta automobila | 1923 — 2021 |
| Proizvođača | 42 |
| Tipova vozila | 13 |
| Regiona | ~400 |
| Država | 50 |

---

## Semantika kolona

### Identifikacija oglasa

| Kolona | Tip | Opis |
|---|---|---|
| `id` | INT64 (PK) | Jedinstveni ID, primarni ključ |
| `url` | STRING | URL pojedinačnog oglasa |
| `region` | STRING | Lokalni Craigslist region |
| `region_url` | STRING | URL ka Craigslist sajtu za specifičan region |

### Identifikacija vozila

| Kolona | Tip | Opis |
|---|---|---|
| `year` | INT | Godište vozila (1923–2021) |
| `manufacturer` | STRING | Proizvođač |
| `model` | STRING | Naziv modela vozila |
| `VIN` | STRING | 17-cifreni broj šasije |
| `type` | STRING | Tip karoserije |

### Tehničke specifikacije

| Kolona | Tip | Opis |
|---|---|---|
| `condition` | STRING | Stanje vozila (new → salvage) |
| `cylinders` | STRING | Broj cilindara (3 do 12) |
| `fuel` | STRING | Gorivo (gas / diesel / hybrid / EV) |
| `odometer` | FLOAT | Kilometraža u miljama |
| `transmission` | STRING | Tip menjača (automatic / manual / other) |
| `drive` | STRING | Pogon (4wd / fwd / rwd) |

### Lokacija

| Kolona | Tip | Opis |
|---|---|---|
| `state` | STRING | Skraćenica savezne države (ca, tx, fl, ny, ...) |
| `county` | STRING | Okrug |
| `lat` | FLOAT | Geografska širina lokacije |
| `long` | FLOAT | Geografska dužina lokacije |

### Cena i vreme

| Kolona | Tip | Opis |
|---|---|---|
| `price` | INT | Cena u USD |
| `posting_date` | DATETIME | Vreme postavljanja oglasa (UTC) |

### Izgled i stanje

| Kolona | Tip | Opis |
|---|---|---|
| `size` | STRING | Veličina vozila (compact / mid-size / full-size / sub-compact) |
| `paint_color` | STRING | Boja vozila |
| `title_status` | STRING | Stanje očuvanosti (clean / salvage / rebuilt / lien / missing) |

### Drugo

| Kolona | Tip | Opis |
|---|---|---|
| `image_url` | STRING | URL slike vozila |
| `description` | TEXT | Tekstualni opis prodavca |

---
## Logička šema baze

### `listings` — glavna kolekcija (~426.880 dokumenata)

| Polje | Tip | Napomena |
|---|---|---|
| `_id` | Int64 (PK) | |
| `url` | String | |
| `price` | Int | |
| `posting_date` | Date | |
| `vehicle { }` | Object (ugneždeno) | `year`, `manufacturer_ref`, `model`, `vin`, `type`, `size`, `paint_color` |
| `specs { }` | Object (ugneždeno) | `condition`, `cylinders`, `fuel`, `odometer_miles`, `transmission`, `drive`, `title_status` |
| `location { }` | Object (ugneždeno) | `region_ref`, `state`, `geo` (GeoJSON Point) |
| `media { }` | Object (ugneždeno) | `image_url`, `description` |

### `regions` (~400 dokumenata)

- `_id` (region name)
- `url`
- `state`
- `listing_count`

### `manufacturers` (42 dokumenta)

- `_id` (ford, toyota, ...)
- `display_name`
- `country`
- `listing_count`

---

## Pitanja

Projekat obrađuje 10 poslovnih pitanja, podeljenih u dve uloge korisnika.

### Uloga: Prodavac

1. Kojih top 10 modela ima najviše aktivnih oglasa (najlikvidniji na tržištu) i kakva im je prosečna cena po godištu?
2. U kojim saveznim državama je određeni model precenjen, a u kojim potcenjen — gde su prilike za arbitražu?
3. Koja zemlja porekla dominira po broju oglasa i ceni, i kako se to razlikuje između istočne i zapadne obale?
4. Koji tipovi karoserije dominiraju u ponudi i kakva je prosečna cena po tipu?
5. Kakva je tržišna distribucija po tipu pogona i koliki je premium za 4wd kod pickup kamiona?

### Uloga: Kupac

6. Kako se prosečna i medijalna cena razlikuje po tipu goriva (benzin, dizel, hibrid, EV) kroz poslednjih 6 godišta (2016–2021)?
7. Kojih top 10 modela najbolje zadržava vrednost — koji imaju najniži godišnji deprecijacioni gubitak?
8. U radijusu od 100 milja od moje lokacije, kojih top 10 vozila u dobrom stanju, cene između $5.000 i $10.000 i sa manje od 100k milja na odometru je najpovoljnije, prikazano zajedno sa udaljenošću?
9. Postoji li statistički značajna razlika između cena vozila sa "clean" i "rebuilt" stanjima za isti model i godište?
10. Koji su najjeftiniji pouzdani auti sa automatskim menjačem ispod $5.000, sortirani po kilometraži?

---