"""
Enterprise ATS Career Ingestion & Deep Merging Pipeline.
Extracts engineering, tech, automotive, medtech, and aerospace companies
from Additional_CSV_Datasets + S&P 500, probes their live ATS boards
(Greenhouse, Lever, SmartRecruiters), and merges them into companies.json
strictly deduplicated.
"""

import os
import re
import csv
import json
import urllib.request
from typing import Set, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "Additional_CSV_Datasets")
COMPANIES_FILE = os.path.join(BASE_DIR, "companies.json")
SP500_FILE = os.path.join(BASE_DIR, "sp500_companies.csv")

TARGET_INDUSTRIES = {
    "automotive", "aviation & aerospace", "aviation and aerospace component manufacturing",
    "defense and space manufacturing", "medical equipment manufacturing", "medical practices",
    "biotechnology research", "pharmaceutical manufacturing", "software development",
    "information technology & services", "telecommunications", "semiconductor manufacturing",
    "electrical & electronic manufacturing", "industrial automation", "rail transportation",
    "machinery manufacturing", "appliances, electrical, and electronics manufacturing"
}

def clean_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r'(?i)\s+(inc\.?|llc|ltd\.?|corp\.?|corporation|gmbh|ag|se|pvt\.?\s+ltd\.?|technologies|solutions|group|systems|holdings|plc)$', '', name).strip()
    return cleaned

def normalize_key(name: str) -> str:
    cleaned = clean_name(name).lower()
    return re.sub(r'[^a-z0-9]', '', cleaned)

def sanitize_token(name: str) -> str:
    clean = clean_name(name)
    return re.sub(r'[^a-z0-9]', '', clean.lower())

def probe_endpoint(token: str) -> Optional[Dict]:
    if not token or len(token) < 2:
        return None
        
    # 1. Greenhouse
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if "jobs" in data and len(data["jobs"]) > 0:
                return {"ats": "greenhouse", "token": token}
    except Exception:
        pass

    # 2. Lever
    try:
        url = f"https://api.lever.co/v0/postings/{token}?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if isinstance(data, list) and len(data) > 0:
                return {"ats": "lever", "token": token}
    except Exception:
        pass

    # 3. SmartRecruiters
    try:
        url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if data.get("totalFound", 0) > 0:
                return {"ats": "smartrecruiters", "token": token}
    except Exception:
        pass

    return None

def probe_candidate(item: tuple) -> Optional[Dict]:
    name, category = item
    token = sanitize_token(name)
    res = probe_endpoint(token)
    if res:
        return {"name": name, "ats": res["ats"], "token": res["token"], "category": category}
    return None

def extract_candidates() -> Dict[str, tuple]:
    candidates = {} # norm_key -> (display_name, category)

    # 1. S&P 500
    if os.path.exists(SP500_FILE):
        try:
            with open(SP500_FILE, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row and row[0]:
                        c_name = row[0].strip()
                        k = normalize_key(c_name)
                        if k and len(k) > 2:
                            candidates[k] = (c_name, "S&P 500 Enterprise")
        except Exception as e:
            print("Error reading S&P 500:", e)

    # 2. Indian Tech Jobs
    p_indian = os.path.join(DATASETS_DIR, "indian_tech_jobs_2026.csv")
    if os.path.exists(p_indian):
        try:
            with open(p_indian, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    c_name = (row.get("company_name") or "").strip()
                    k = normalize_key(c_name)
                    if k and len(k) > 2 and k not in candidates:
                        candidates[k] = (c_name, "Indian Tech & Engineering")
        except Exception as e:
            print("Error reading Indian tech jobs:", e)

    # 3. Companies 2023 Q4 (Filtered for automotive, aerospace, medtech, software)
    p_q4 = os.path.join(DATASETS_DIR, "companies-2023-q4-sm.csv")
    if os.path.exists(p_q4):
        try:
            count = 0
            with open(p_q4, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    count += 1
                    ind = (row.get("industry") or "").strip().lower()
                    if ind in TARGET_INDUSTRIES:
                        c_name = (row.get("name") or "").strip()
                        k = normalize_key(c_name)
                        if k and len(k) > 2 and k not in candidates:
                            candidates[k] = (c_name, ind.title())
                    if count >= 300000:
                        break
        except Exception as e:
            print("Error reading Q4 dataset:", e)

    # 4. Free Company Dataset (PDL)
    p_pdl = os.path.join(DATASETS_DIR, "free_company_dataset.csv")
    if os.path.exists(p_pdl):
        try:
            count = 0
            with open(p_pdl, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    count += 1
                    ind = (row.get("industry") or "").strip().lower()
                    if any(t in ind for t in ["automotive", "aerospace", "aviation", "defense", "medical", "semiconductor", "computer software", "information technology"]):
                        c_name = (row.get("name") or "").strip()
                        k = normalize_key(c_name)
                        if k and len(k) > 2 and k not in candidates:
                            candidates[k] = (c_name, ind.title())
                    if count >= 250000:
                        break
        except Exception as e:
            print("Error reading PDL dataset:", e)

    return candidates

def main():
    print("=== Multi-Dataset Career Portal Discovery & Ingestion ===")
    
    # 1. Load existing companies.json
    existing = []
    if os.path.exists(COMPANIES_FILE):
        with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
            
    existing_keys = {normalize_key(c["name"]) for c in existing}
    print(f"Existing verified companies in companies.json: {len(existing)}")

    # 2. Extract and filter candidates
    print("Extracting candidates across all 4 datasets...")
    candidates = extract_candidates()
    print(f"Total deduplicated candidates extracted: {len(candidates):,}")

    # Remove already existing companies
    unprobed = [v for k, v in candidates.items() if k not in existing_keys]
    print(f"Candidates pending ATS verification: {len(unprobed):,}")

    # 3. Probe top chunk in parallel with 35 workers
    # We will probe the first 2,000 priority candidates
    batch_to_probe = unprobed[:2000]
    print(f"\nProbing {len(batch_to_probe)} high-priority enterprise candidates across Greenhouse, Lever, and SmartRecruiters (35 threads)...")

    new_discovered = []
    with ThreadPoolExecutor(max_workers=35) as executor:
        futures = {executor.submit(probe_candidate, item): item for item in batch_to_probe}
        for f in as_completed(futures):
            res = f.result()
            if res:
                new_discovered.append(res)
                print(f"  [VERIFIED ATS] {res['name']} -> {res['ats'].upper()} ({res['token']})")

    print(f"\nVerification pass completed! Discovered {len(new_discovered)} live career ATS portals.")

    # 4. Merge deduplicated
    added = 0
    for d in new_discovered:
        k = normalize_key(d["name"])
        if k not in existing_keys:
            existing.append(d)
            existing_keys.add(k)
            added += 1

    with open(COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    print("\n" + "="*60)
    print(f"SUCCESSFULLY MERGED {added} NEW ENTERPRISE CAREER ENDPOINTS")
    print(f"Total Verified Companies in companies.json: {len(existing)}")
    print("="*60)

if __name__ == "__main__":
    main()

