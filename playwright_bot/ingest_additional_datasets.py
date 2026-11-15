"""
High-Speed Chunked Dataset Ingestion & Deduplication Pipeline.

Processes:
1. indian_tech_jobs_2026.csv (6,993 Indian tech & engineering employers)
2. companies-2023-q4-sm.csv (Filtered for high-relevance industries & scale: Automotive, Medical Devices, Aerospace, Software, Defense)
3. free_company_dataset.csv (People Data Labs bulk dataset: filtered for relevant industries & enterprise scale)

Deduplication Rules:
- Case-insensitive clean company root match.
- Strips legal suffixes (Inc, LLC, Ltd, Pvt Ltd, GmbH, AG, SE, Corp, Systems, Technologies).
- Zero duplicate entries in companies.json.
- Verifies live ATS capability (Greenhouse, Lever, SmartRecruiters, Workday) before or during ingestion.
"""

import os
import re
import csv
import json
from typing import Set, List, Dict
from ats_company_prober import probe_company, sanitize_token

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "Additional_CSV_Datasets")
COMPANIES_FILE = os.path.join(BASE_DIR, "companies.json")

# Target engineering & tech industries relevant to ALM, PLM, Embedded, Systems Engineering
TARGET_INDUSTRIES = {
    "automotive", "aviation & aerospace", "aviation and aerospace component manufacturing",
    "defense and space manufacturing", "medical equipment manufacturing", "medical practices",
    "biotechnology research", "pharmaceutical manufacturing", "software development",
    "information technology & services", "telecommunications", "semiconductor manufacturing",
    "electrical & electronic manufacturing", "industrial automation", "rail transportation",
    "machinery manufacturing", "appliances, electrical, and electronics manufacturing"
}

TARGET_SIZES = {"51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"}

def clean_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r'(?i)\s+(inc\.?|llc|ltd\.?|corp\.?|corporation|gmbh|ag|se|pvt\.?\s+ltd\.?|technologies|solutions|group|systems|holdings|plc)$', '', name).strip()
    return cleaned

def normalize_key(name: str) -> str:
    cleaned = clean_name(name).lower()
    return re.sub(r'[^a-z0-9]', '', cleaned)

def extract_from_indian_tech_jobs(path: str) -> Set[str]:
    print(f"\n[1/3] Ingesting Indian Tech Jobs dataset ({os.path.basename(path)})...")
    comps = set()
    if not os.path.exists(path):
        return comps
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = (row.get("company_name") or "").strip()
            if c and len(c) > 2:
                comps.add(c)
    print(f"  -> Extracted {len(comps)} unique company names from Indian tech jobs.")
    return comps

def extract_from_companies_q4(path: str, max_limit: int = 50000) -> Set[str]:
    print(f"\n[2/3] Streaming & filtering {os.path.basename(path)} (Automotive, MedTech, Aero, Software)...")
    comps = set()
    if not os.path.exists(path):
        return comps
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            ind = (row.get("industry") or "").strip().lower()
            size = (row.get("size") or "").strip()
            name = (row.get("name") or "").strip()

            # Target mid-to-enterprise engineering/tech companies
            if ind in TARGET_INDUSTRIES and size in TARGET_SIZES and name:
                comps.add(name)
                if len(comps) >= max_limit:
                    break
            if count % 200000 == 0:
                print(f"  ...scanned {count:,} records (found {len(comps):,} high-fit targets)")
    print(f"  -> Extracted {len(comps)} filtered enterprise targets from Q4 dataset.")
    return comps

def extract_from_pdl(path: str, max_limit: int = 50000) -> Set[str]:
    print(f"\n[3/3] Streaming & filtering People Data Labs dataset ({os.path.basename(path)})...")
    comps = set()
    if not os.path.exists(path):
        return comps
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            ind = (row.get("industry") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if any(t in ind for t in ["automotive", "aerospace", "aviation", "defense", "medical", "semiconductor", "computer software"]) and name:
                comps.add(name)
                if len(comps) >= max_limit:
                    break
            if count % 300000 == 0:
                print(f"  ...scanned {count:,} PDL records (found {len(comps):,} high-fit targets)")
    print(f"  -> Extracted {len(comps)} filtered targets from PDL dataset.")
    return comps

def main():
    # 1. Load existing companies.json
    existing_list = []
    if os.path.exists(COMPANIES_FILE):
        with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
            existing_list = json.load(f)

    existing_keys = {normalize_key(c["name"]) for c in existing_list}
    print(f"Current companies in database: {len(existing_list)} verified ATS endpoints.")

    # 2. Extract from all 3 datasets
    p_indian = os.path.join(DATASETS_DIR, "indian_tech_jobs_2026.csv")
    p_q4 = os.path.join(DATASETS_DIR, "companies-2023-q4-sm.csv")
    p_pdl = os.path.join(DATASETS_DIR, "free_company_dataset.csv")

    indian_comps = extract_from_indian_tech_jobs(p_indian)
    q4_comps = extract_from_companies_q4(p_q4, max_limit=30000)
    pdl_comps = extract_from_pdl(p_pdl, max_limit=30000)

    # 3. Combine and strictly deduplicate
    all_raw_candidates = indian_comps.union(q4_comps).union(pdl_comps)
    print(f"\nTotal raw aggregated candidate pool: {len(all_raw_candidates):,} companies.")

    unique_to_probe = {}
    for name in all_raw_candidates:
        k = normalize_key(name)
        if k and len(k) > 2 and k not in existing_keys and k not in unique_to_probe:
            unique_to_probe[k] = name

    print(f"Brand-new unique enterprise candidates to evaluate: {len(unique_to_probe):,} companies.")

    # 4. Probe top batch concurrently for instant expansion
    probe_sample = list(unique_to_probe.values())[:300]
    print(f"\nProbing batch of {len(probe_sample)} prioritized candidates across Greenhouse, Lever, and SmartRecruiters...")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    discovered = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(probe_company, n): n for n in probe_sample}
        for f in as_completed(futures):
            res = f.result()
            if res:
                discovered.append(res)
                print(f"  [ATS FOUND] {res['name']} -> {res['ats'].upper()} ({res['token']})")

    # 5. Merge verified endpoints strictly into companies.json
    added_count = 0
    for d in discovered:
        k = normalize_key(d["name"])
        if k not in existing_keys:
            existing_list.append(d)
            existing_keys.add(k)
            added_count += 1

    with open(COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_list, f, indent=2)

    print(f"\n==================================================")
    print(f"SUCCESS: Added {added_count} brand-new verified ATS endpoints.")
    print(f"Zero duplicates guaranteed: Database total is now {len(existing_list)} companies.")
    print(f"All saved to: {COMPANIES_FILE}")
    print(f"==================================================")

if __name__ == "__main__":
    main()

