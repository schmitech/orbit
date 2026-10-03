#!/usr/bin/env python3
"""One-off generator for the CP2H demo CSVs. Not a long-term maintained script."""
import csv
import random
from datetime import date, timedelta
from faker import Faker

random.seed(42)
fake = Faker()
Faker.seed(42)

CANADIAN_CITIES = [
    ("Ottawa", "ON"), ("Toronto", "ON"), ("Hamilton", "ON"), ("Kingston", "ON"),
    ("Montreal", "QC"), ("Quebec City", "QC"), ("Laval", "QC"), ("Sherbrooke", "QC"),
    ("Vancouver", "BC"), ("Burnaby", "BC"), ("Victoria", "BC"), ("Surrey", "BC"),
    ("Calgary", "AB"), ("Edmonton", "AB"), ("Winnipeg", "MB"), ("Saskatoon", "SK"),
    ("Regina", "SK"), ("Halifax", "NS"), ("Fredericton", "NB"), ("St. John's", "NL"),
]

BIOTECH_SUFFIXES = ["Biologics", "Therapeutics", "Biosciences", "Life Sciences", "Biomanufacturing", "Vaccines"]
ACADEMIC_HOSTS = [
    ("University of Ottawa", "Ottawa", "ON"), ("McMaster University", "Hamilton", "ON"),
    ("Dalhousie University", "Halifax", "NS"), ("University of Toronto", "Toronto", "ON"),
    ("University of British Columbia", "Vancouver", "BC"), ("Université Laval", "Quebec City", "QC"),
    ("University of Alberta", "Edmonton", "AB"), ("University of Manitoba", "Winnipeg", "MB"),
    ("The Ottawa Hospital Research Institute", "Ottawa", "ON"),
]
PARTNER_NETWORKS = ["CP2H", "BioCanRx", "Canadian Immunization Research Network", "independent"]
FACILITY_TYPES = ["vaccine", "viral_vector", "cell_therapy", "antibody", "mRNA"]
STATUSES = ["operational", "under_construction", "planned"]

PATHOGENS = ["influenza", "coronavirus", "RSV", "mpox", "norovirus", "H5N1 avian influenza"]
PHASES = ["Preclinical", "Phase I", "Phase II", "Phase III", "Approved"]
TRIAL_STATUSES = ["active", "completed", "paused", "terminated"]
SPONSOR_SUFFIXES = ["Therapeutics", "Biosciences", "Vaccines Inc.", "Biopharma", "Life Sciences"]


def gen_facilities(n):
    rows = []
    for i in range(1, n + 1):
        is_academic = random.random() < 0.3
        if is_academic:
            org, city, province = random.choice(ACADEMIC_HOSTS)
        else:
            org = f"{fake.last_name()} {random.choice(BIOTECH_SUFFIXES)}"
            city, province = random.choice(CANADIAN_CITIES)
        facility_type = random.choice(FACILITY_TYPES)
        status = random.choices(STATUSES, weights=[0.6, 0.25, 0.15])[0]
        rows.append({
            "facility_id": i,
            "facility_name": f"{org} {facility_type.replace('_', ' ').title()} Facility",
            "organization": org,
            "province": province,
            "city": city,
            "facility_type": facility_type,
            "capacity_liters": random.choice([500, 1000, 2000, 5000, 10000, 20000, 50000]),
            "status": status,
            "gmp_certified": status == "operational" and random.random() < 0.8,
            "commissioned_year": random.randint(2015, 2025) if status == "operational" else None,
            "partner_network": random.choice(PARTNER_NETWORKS),
        })
    return rows


def gen_trials(n, facility_ids):
    rows = []
    start = date(2022, 1, 1)
    for i in range(1, n + 1):
        pathogen = random.choice(PATHOGENS)
        candidate = f"{pathogen.split()[0].upper()}-{random.choice(['VAC','MAB','THX'])}-{random.randint(100,999)}"
        sponsor = f"{fake.last_name()} {random.choice(SPONSOR_SUFFIXES)}"
        phase = random.choices(PHASES, weights=[0.25, 0.25, 0.2, 0.2, 0.1])[0]
        status = random.choices(TRIAL_STATUSES, weights=[0.55, 0.3, 0.1, 0.05])[0]
        offset_days = random.randint(0, 1200)
        rows.append({
            "trial_id": i,
            "candidate_name": candidate,
            "pathogen_target": pathogen,
            "trial_phase": phase,
            "sponsor_organization": sponsor,
            "facility_id": random.choice(facility_ids),
            "start_date": (start + timedelta(days=offset_days)).isoformat(),
            "status": status,
            "enrollment_count": random.randint(20, 1200),
            "country": "Canada",
        })
    return rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    facilities = gen_facilities(60)
    facility_ids = [r["facility_id"] for r in facilities]
    trials = gen_trials(220, facility_ids)

    write_csv(
        "biomanufacturing_facilities.csv", facilities,
        ["facility_id", "facility_name", "organization", "province", "city", "facility_type",
         "capacity_liters", "status", "gmp_certified", "commissioned_year", "partner_network"],
    )
    write_csv(
        "clinical_trials.csv", trials,
        ["trial_id", "candidate_name", "pathogen_target", "trial_phase", "sponsor_organization",
         "facility_id", "start_date", "status", "enrollment_count", "country"],
    )
    print(f"facilities={len(facilities)} trials={len(trials)}")
