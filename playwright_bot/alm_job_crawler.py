"""
Global Job Search & Career Portal Crawler for ALM Tools:
Targets: 'Codebeamer', 'PTC Integrity', 'MKS Integrity'

Engine Architecture:
1. Geo-Priority Hierarchy (Relocation & German Pension Friendly):
   - Tier 1: India (Bengaluru, Hyderabad, Pune, Gurugram, Chennai, etc.) - Top Priority.
   - Tier 2: Non-Schengen Global (USA, UK, Australia, Canada, New Zealand, Russia, etc.) - High Priority.
   - Tier 3: Other Non-EU / Global (Japan, Brazil, Mexico, etc.) - Alternate.
   - Tier 4: Schengen / EU (Germany, France, Sweden, etc.) - Last Resort (due to pension waiting rules).
2. Multi-Engine Sources:
   - Phase 0: India Tech Engine (Naukri.com via Playwright)
   - Phase 1: Direct Enterprise Career Portals (Workday APIs: Medtronic, Stryker, Philips, etc.)
   - Phase 2: Global Tech Aggregators (Indeed, Glassdoor, LinkedIn)
3. Advanced Cluster Deduplication:
   - Unifies company variations (e.g. 'Bosch' vs 'Bosch Group', 'EDAG' vs 'EDAG Engineering')
   - Groups identical postings into a single row with multi-portal buttons side-by-side.
4. Experience Extraction Engine:
   - Scans and resolves max required tenure (e.g. '8+ Yrs', '5 - 7 Yrs').
5. Interactive Web Dashboard & Local Server:
   - Full search, filter, status toggles (Applied / To Apply), and live web crawl trigger.
"""

import os
import re
import json
import time
import html
import datetime
import argparse
from typing import List, Dict, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import pandas as pd
from jobspy import scrape_jobs

try:
    from naukri_scraper import scrape_naukri_jobs
except ImportError:
    scrape_naukri_jobs = None

try:
    from ats_engine import ATSManager
except ImportError:
    ATSManager = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "crawler_state.json")
REPORT_FILE = os.path.join(BASE_DIR, "matched_jobs_report.html")
PROGRESS_FILE = os.path.join(BASE_DIR, "crawler_progress.json")

class SessionTracker:
    """Tracks session progress towards new job limit and updates progress file for Web UI."""
    def __init__(self, target_total: int, new_limit: int):
        self.target_total = target_total
        self.new_limit = new_limit
        self.newly_added = 0
        self.current_stage = "Initializing session..."
        self.is_running = True

    def should_stop(self, total_current_jobs: int) -> bool:
        if self.new_limit > 0:
            return self.newly_added >= self.new_limit
        if self.target_total > 0 and total_current_jobs >= self.target_total:
            return True
        return False

    def on_job_added(self, total_current_jobs: int):
        self.newly_added += 1
        self.save_progress(total_current_jobs, is_running=True)

    def set_stage(self, stage_name: str, total_current_jobs: int):
        self.current_stage = stage_name
        self.save_progress(total_current_jobs, is_running=True)

    def save_progress(self, total_current_jobs: int, is_running: bool = True):
        self.is_running = is_running
        target_display = self.new_limit if self.new_limit > 0 else 50
        percent = int(min(100, (self.newly_added / max(1, target_display)) * 100))
        progress_data = {
            "is_running": self.is_running,
            "stage": self.current_stage,
            "new_found": self.newly_added,
            "target_new": target_display,
            "total_jobs": total_current_jobs,
            "percent": percent,
            "updated_at": datetime.datetime.now().strftime("%I:%M:%S %p")
        }
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, indent=2)
        except Exception:
            pass

TARGET_KEYWORDS = ["Codebeamer", "PTC Integrity", "MKS Integrity"]
KEYWORD_PATTERN = re.compile(r"\b(codebeamer|ptc\s+integrity|mks\s+integrity)\b", re.IGNORECASE)

INDIA_LOCATION_PATTERN = re.compile(
    r"\b(india|bengaluru|bangalore|hyderabad|pune|gurgaon|gurugram|noida|chennai|mumbai|delhi|ahmedabad|kolkata|coimbatore|karnataka|telangana|maharashtra|haryana|tamil\s+nadu|ka|ts|mh|hr|tn)\b",
    re.IGNORECASE
)

SCHENGEN_COUNTRIES = {
    "germany", "france", "austria", "belgium", "czech republic", "czechia",
    "denmark", "estonia", "finland", "greece", "hungary", "iceland", "italy",
    "latvia", "liechtenstein", "lithuania", "luxembourg", "malta", "netherlands",
    "norway", "poland", "portugal", "slovakia", "slovenia", "spain", "sweden",
    "switzerland", "croatia"
}

NON_SCHENGEN_PRIORITY_COUNTRIES = {
    "usa", "united states", "uk", "united kingdom", "canada", "australia",
    "new zealand", "russia", "uae", "united arab emirates", "singapore"
}

COMPANIES_FILE = os.path.join(BASE_DIR, "companies.json")

def load_target_companies() -> List[Dict]:
    """Loads enterprise company list from companies.json or falls back to built-in list."""
    if os.path.exists(COMPANIES_FILE):
        try:
            with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return ENTERPRISE_WORKDAY_COMPANIES

ENTERPRISE_WORKDAY_COMPANIES = [
    {"name": "Medtronic", "tenant": "medtronic", "site": "MedtronicCareers", "domain": "wd1"},
    {"name": "Stryker", "tenant": "stryker", "site": "StrykerCareers", "domain": "wd1"},
    {"name": "Philips", "tenant": "philips", "site": "External", "domain": "wd3"},
    {"name": "Abbott", "tenant": "abbott", "site": "abbottcareers", "domain": "wd5"},
    {"name": "Boston Scientific", "tenant": "bostonscientific", "site": "bsc", "domain": "wd1"},
    {"name": "Baxter", "tenant": "baxter", "site": "Careers", "domain": "wd1"},
    {"name": "Siemens Healthineers", "tenant": "siemenshealthineers", "site": "shscareers", "domain": "wd3"},
    {"name": "ZF Group", "tenant": "zf", "site": "ZFCareers", "domain": "wd3"},
    {"name": "Continental", "tenant": "continental", "site": "careers", "domain": "wd3"},
    {"name": "Valeo", "tenant": "valeo", "site": "Careers", "domain": "wd3"},
    {"name": "Magna International", "tenant": "magna", "site": "Careers", "domain": "wd3"},
    {"name": "Collins Aerospace (RTX)", "tenant": "rtx", "site": "RTX", "domain": "wd5"},
    {"name": "General Electric", "tenant": "ge", "site": "GECareers", "domain": "wd5"},
    {"name": "Honeywell", "tenant": "honeywell", "site": "HoneywellCareers", "domain": "wd3"},
]

def load_state() -> Dict:
    """Loads existing state from crawler_state.json or returns initial empty state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                if "company_cursor" not in state:
                    state["company_cursor"] = 0
                if "scan_cycle" not in state:
                    state["scan_cycle"] = 1
                return state
        except Exception as e:
            print(f"[Warning] Could not load state file: {e}. Starting fresh.")
    return {
        "processed_companies": {},
        "matched_jobs": [],
        "seen_job_urls": [],
        "company_cursor": 0,
        "scan_cycle": 1
    }

def save_state(state: Dict):
    """Saves current state to crawler_state.json atomically."""
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    os.rename(temp_file, STATE_FILE)

def clean_company_name(name: str) -> str:
    """Standardizes company names for deduplication."""
    if not name or pd.isna(name):
        return "Unknown Company"
    cleaned = str(name).strip()
    cleaned = re.sub(r'(?i)\s+(inc\.?|llc|ltd\.?|corp\.?|corporation|gmbh|ag|se|pvt\.?\s+ltd\.?|technologies|solutions|group|systems|safety systems|technology usa)$', '', cleaned).strip()
    return cleaned

def get_company_brand_root(name: str) -> str:
    """Extracts fundamental brand root (e.g. 'Bosch Group' -> 'bosch', 'EDAG Engineering' -> 'edag')."""
    cleaned = clean_company_name(name).lower()
    root = re.split(r'[\s\-_,]', cleaned)[0]
    return re.sub(r'[^a-z0-9]', '', root)

def normalize_title(title: str) -> str:
    """Normalizes job titles for fuzzy clustering."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', t)
    t = re.sub(r'[_\-#\/\\:]', ' ', t)
    t_words = [w for w in t.split() if w not in ['senior', 'sr', 'lead', 'principal', 'staff', 'junior', 'jr', 'engineer', 'developer', 'consultant', 'm', 'f', 'd', 'w', 'all', 'genders']]
    t_norm = ''.join(t_words[:3]) or re.sub(r'[^a-z0-9]', '', t[:14])
    return t_norm

def classify_location_tier(loc_str: str) -> Tuple[int, str]:
    """
    Classifies location according to the 4-tier relocation strategy:
    1: India
    2: Non-Schengen Priority (USA, UK, Australia, Canada, NZ, Russia)
    3: Other Non-EU Global
    4: Schengen / EU (Last Resort)
    """
    if not loc_str:
        return (3, "🌐 Tier 3: Global Non-EU")
    loc_lower = loc_str.lower()

    if is_india_location(loc_str):
        return (1, "🇮🇳 Tier 1: India")

    for c in SCHENGEN_COUNTRIES:
        if re.search(r'\b' + re.escape(c) + r'\b', loc_lower):
            return (4, "⚠️ Tier 4: Schengen (Last Resort)")

    for c in NON_SCHENGEN_PRIORITY_COUNTRIES:
        if re.search(r'\b' + re.escape(c) + r'\b', loc_lower):
            return (2, "🌏 Tier 2: Non-Schengen")

    return (3, "🌐 Tier 3: Global Non-EU")

def make_job_cluster_key(company: str, title: str, location: str) -> str:
    """Creates a unified deduplication cluster key."""
    c_root = get_company_brand_root(company)
    t_norm = normalize_title(title)
    is_ind = is_india_location(location)
    loc_norm = "india" if is_ind else re.sub(r'[^a-z0-9]', '', location.lower()[:12])
    return f"{c_root}_{t_norm}_{loc_norm}"

def is_india_location(loc_str: str) -> bool:
    """Checks whether the given location string belongs to India."""
    if not loc_str:
        return False
    return bool(INDIA_LOCATION_PATTERN.search(loc_str))

def extract_matched_keywords(text: str) -> List[str]:
    """Returns list of specific target keywords found in text."""
    matches = set()
    if not text:
        return []
    text_lower = text.lower()
    if "codebeamer" in text_lower:
        matches.add("Codebeamer")
    if re.search(r"\bptc\s+integrity\b", text_lower):
        matches.add("PTC Integrity")
    if re.search(r"\bmks\s+integrity\b", text_lower):
        matches.add("MKS Integrity")
    return sorted(list(matches))

def extract_experience(text: str) -> str:
    """
    Scans job description and extracts experience requirements.
    In case multiple experience requirements are mentioned (e.g. 4+ yrs Python, 8+ yrs SDLC),
    picks the maximum requirement as the overall role requirement.
    """
    if not text:
        return "Not Specified"

    decoded_text = html.unescape(text)
    decoded_text = re.sub(r'<[^>]+>', ' ', decoded_text)
    clean_text = " " + re.sub(r'\s+', ' ', decoded_text) + " "
    found_candidates = []

    # 1. Range matches
    range_pattern = re.compile(r'\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)\b', re.IGNORECASE)
    for m in range_pattern.finditer(clean_text):
        val1, val2 = int(m.group(1)), int(m.group(2))
        if 0 < val1 <= 30 and 0 < val2 <= 30:
            low, high = min(val1, val2), max(val1, val2)
            found_candidates.append((high, low, True, f"{low} - {high} Yrs"))

    # 2. Plus matches
    plus_pattern = re.compile(r'\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b', re.IGNORECASE)
    for m in plus_pattern.finditer(clean_text):
        val = int(m.group(1))
        if 1 <= val <= 30:
            found_candidates.append((val, val, False, f"{val}+ Yrs"))

    # 3. Minimum / at least matches
    min_pattern = re.compile(r'\b(?:minimum|min|at\s+least|around)\s+(\d{1,2})\s*(?:years?|yrs?)\b', re.IGNORECASE)
    for m in min_pattern.finditer(clean_text):
        val = int(m.group(1))
        if 1 <= val <= 30:
            found_candidates.append((val, val, False, f"{val}+ Yrs"))

    # 4. Standard "X years of experience"
    std_pattern = re.compile(r'\b(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b', re.IGNORECASE)
    for m in std_pattern.finditer(clean_text):
        val = int(m.group(1))
        if 1 <= val <= 30:
            found_candidates.append((val, val, False, f"{val}+ Yrs"))

    if not found_candidates:
        return "Not Specified"

    found_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return found_candidates[0][3]

def merge_or_append_job(matched_jobs: List[Dict], new_entry: Dict) -> bool:
    """
    Checks if an existing job cluster matches company, normalized title, and location.
    If match found: merges portal links into application_links.
    If no match found: appends as a new cluster.
    """
    cluster_key = new_entry.get("cluster_key") or make_job_cluster_key(
        new_entry["company"], new_entry["title"], new_entry["location"]
    )
    new_entry["cluster_key"] = cluster_key

    tier_num, tier_label = classify_location_tier(new_entry["location"])
    new_entry["tier_num"] = tier_num
    new_entry["tier_label"] = tier_label

    if "application_links" not in new_entry or not new_entry["application_links"]:
        new_entry["application_links"] = [{
            "portal": new_entry.get("source", "Apply"),
            "url": new_entry["job_url"]
        }]

    for existing in matched_jobs:
        ex_key = existing.get("cluster_key") or make_job_cluster_key(
            existing["company"], existing["title"], existing["location"]
        )
        existing["cluster_key"] = ex_key

        if ex_key == cluster_key:
            existing_urls = {link["url"] for link in existing.get("application_links", [])}
            for link in new_entry["application_links"]:
                if link["url"] not in existing_urls:
                    existing["application_links"].append(link)
                    existing_urls.add(link["url"])

            existing_kws = set(existing.get("matched_keywords", []))
            existing_kws.update(new_entry.get("matched_keywords", []))
            existing["matched_keywords"] = sorted(list(existing_kws))

            if existing.get("experience") in (None, "Not Specified") and new_entry.get("experience") != "Not Specified":
                existing["experience"] = new_entry["experience"]

            # Retain or refresh ATS evaluation info
            for k in ("best_cv", "ats_score", "recommended_certificates"):
                if k in new_entry and k not in existing:
                    existing[k] = new_entry[k]

            return False

    matched_jobs.append(new_entry)
    return True

def search_naukri_career_portal(target_limit: int, state: Dict, tracker: SessionTracker = None) -> int:
    """Scrapes Naukri.com India for ALM keywords."""
    if not scrape_naukri_jobs:
        return 0

    if tracker:
        tracker.set_stage("Phase 0: Scanning Naukri.com India for ALM openings...", len(state["matched_jobs"]))

    added = 0
    processed = state["processed_companies"]
    seen_urls = set(state.get("seen_job_urls", []))

    naukri_jobs = scrape_naukri_jobs(max_pages_per_keyword=2)

    for item in naukri_jobs:
        if tracker and tracker.should_stop(len(state["matched_jobs"])):
            break
        elif len(state["matched_jobs"]) >= target_limit:
            break

        c_name = item["company"]
        comp_key = clean_company_name(c_name).lower()
        cluster_k = make_job_cluster_key(c_name, item["title"], item["location"])

        job_entry = {
            "company": c_name,
            "title": item["title"],
            "location": item["location"],
            "job_url": item["job_url"],
            "experience": item["experience"],
            "matched_keywords": item["matched_keywords"],
            "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Naukri",
            "is_india": True,
            "cluster_key": cluster_k,
            "application_links": [
                {"portal": "Naukri", "url": item["job_url"]}
            ]
        }

        is_new = merge_or_append_job(state["matched_jobs"], job_entry)
        state["seen_job_urls"].append(item["job_url"])
        if is_new:
            added += 1
            if tracker:
                tracker.on_job_added(len(state["matched_jobs"]))
            print(f"  [NAUKRI MATCH #{len(state['matched_jobs'])}] {item['company']} - {item['title']} [{item['experience']}] ({item['location']})")
        else:
            print(f"  [MERGED NAUKRI LINK] Added link for: {item['company']} - {item['title']}")

        processed[comp_key] = {
            "name": c_name,
            "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Found matches on Naukri India",
            "source": "Naukri.com"
        }

    save_state(state)
    generate_html_report(state)
    return added

def search_workday_careers(target_limit: int, state: Dict, tracker: SessionTracker = None) -> int:
    """Queries enterprise Workday Career APIs directly."""
    import urllib.request
    import urllib.error

    added = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print("\n--- Phase 1: Enterprise Direct Career Portals (Universal Multi-ATS Engine) ---")
    processed = state["processed_companies"]
    seen_urls = set(state.get("seen_job_urls", []))
    all_companies = load_target_companies()

    # Sequential Circular Cursor: Never re-visit already checked companies until full cycle completes
    total_companies = len(all_companies)
    start_cursor = state.get("company_cursor", 0) % max(1, total_companies)
    current_cycle = state.get("scan_cycle", 1)

    # Order companies starting from cursor
    ordered_companies = all_companies[start_cursor:] + all_companies[:start_cursor]

    print(f"[Career Site Queue] Starting at Company #{start_cursor + 1}/{total_companies} (Cycle {current_cycle}).")

    def fetch_company_postings(comp: Dict) -> Tuple[str, str, List[Dict]]:
        c_name = comp["name"]
        comp_k = clean_company_name(c_name).lower()
        ats_type = comp.get("ats", "workday").lower()
        comp_matches = []

        # 1. WORKDAY ATS
        if ats_type == "workday":
            tenant = comp["tenant"]
            site = comp["site"]
            domain = comp.get("domain", "wd1")
            base_endpoint = f"https://{tenant}.{domain}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
            search_endpoint = f"{base_endpoint}/jobs"

            for keyword in TARGET_KEYWORDS:
                payload = json.dumps({
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": 0,
                    "searchText": keyword
                }).encode("utf-8")
                req = urllib.request.Request(search_endpoint, data=payload, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        postings = data.get("jobPostings", [])
                        for post in postings:
                            ext_path = post.get("externalPath")
                            title = post.get("title", "Unknown Role")
                            location = post.get("locationsText", "Not specified")
                            public_job_url = f"https://{tenant}.{domain}.myworkdayjobs.com/en-US/{site}{ext_path}"

                            detail_url = f"{base_endpoint}{ext_path}"
                            det_req = urllib.request.Request(detail_url, headers=headers)
                            try:
                                with urllib.request.urlopen(det_req, timeout=8) as d_resp:
                                    d_data = json.loads(d_resp.read().decode("utf-8", errors="ignore"))
                                    job_info = d_data.get("jobPostingInfo", {})
                                    raw_desc = job_info.get("jobDescription", "")
                                    loc_val = job_info.get("location") or location

                                    matches = extract_matched_keywords(raw_desc)
                                    if matches:
                                        exp_req = extract_experience(raw_desc)
                                        is_ind = is_india_location(loc_val or location)
                                        cluster_k = make_job_cluster_key(c_name, title, loc_val or location)
                                        job_entry = {
                                            "company": c_name,
                                            "title": title,
                                            "location": loc_val or "Not specified",
                                            "job_url": public_job_url,
                                            "experience": exp_req,
                                            "matched_keywords": matches,
                                            "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            "source": "Career Site (Workday)",
                                            "is_india": is_ind,
                                            "cluster_key": cluster_k,
                                            "application_links": [
                                                {"portal": "Direct Career Site", "url": public_job_url}
                                            ]
                                        }
                                        comp_matches.append(job_entry)
                            except Exception:
                                pass
                except Exception:
                    pass

        # 2. GREENHOUSE ATS
        elif ats_type == "greenhouse":
            token = comp.get("token")
            if token:
                gh_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
                gh_req = urllib.request.Request(gh_url, headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(gh_req, timeout=10) as resp:
                        gh_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        jobs_list = gh_data.get("jobs", [])
                        for j in jobs_list:
                            title = j.get("title", "Unknown Role")
                            loc_info = j.get("location", {})
                            location = loc_info.get("name", "Not specified") if isinstance(loc_info, dict) else str(loc_info)
                            content = j.get("content", "")
                            job_url = j.get("absolute_url", f"https://boards.greenhouse.io/{token}/jobs/{j.get('id')}")

                            matches = extract_matched_keywords(f"{title} {content}")
                            if matches:
                                exp_req = extract_experience(content)
                                is_ind = is_india_location(location)
                                cluster_k = make_job_cluster_key(c_name, title, location)
                                job_entry = {
                                    "company": c_name,
                                    "title": title,
                                    "location": location,
                                    "job_url": job_url,
                                    "experience": exp_req,
                                    "matched_keywords": matches,
                                    "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "source": "Career Site (Greenhouse)",
                                    "is_india": is_ind,
                                    "cluster_key": cluster_k,
                                    "application_links": [
                                        {"portal": "Direct Career Site", "url": job_url}
                                    ]
                                }
                                comp_matches.append(job_entry)
                except Exception:
                    pass

        # 3. LEVER ATS
        elif ats_type == "lever":
            token = comp.get("token")
            if token:
                lever_url = f"https://api.lever.co/v0/postings/{token}?mode=json"
                lev_req = urllib.request.Request(lever_url, headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(lev_req, timeout=10) as resp:
                        lev_jobs = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        for j in lev_jobs:
                            title = j.get("text", "Unknown Role")
                            cats = j.get("categories", {})
                            location = cats.get("location", "Not specified")
                            desc = j.get("descriptionPlain", "") or j.get("description", "")
                            job_url = j.get("hostedUrl", f"https://jobs.lever.co/{token}/{j.get('id')}")

                            matches = extract_matched_keywords(f"{title} {desc}")
                            if matches:
                                exp_req = extract_experience(desc)
                                is_ind = is_india_location(location)
                                cluster_k = make_job_cluster_key(c_name, title, location)
                                job_entry = {
                                    "company": c_name,
                                    "title": title,
                                    "location": location,
                                    "job_url": job_url,
                                    "experience": exp_req,
                                    "matched_keywords": matches,
                                    "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "source": "Career Site (Lever)",
                                    "is_india": is_ind,
                                    "cluster_key": cluster_k,
                                    "application_links": [
                                        {"portal": "Direct Career Site", "url": job_url}
                                    ]
                                }
                                comp_matches.append(job_entry)
                except Exception:
                    pass

        # 4. SMARTRECRUITERS ATS
        elif ats_type == "smartrecruiters":
            token = comp.get("token")
            if token:
                for keyword in TARGET_KEYWORDS:
                    sr_url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?q={urllib.parse.quote(keyword)}&limit=20"
                    sr_req = urllib.request.Request(sr_url, headers={"User-Agent": "Mozilla/5.0"})
                    try:
                        with urllib.request.urlopen(sr_req, timeout=8) as resp:
                            sr_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                            postings = sr_data.get("content", [])
                            for p in postings:
                                title = p.get("name", "Unknown Role")
                                loc_dict = p.get("location", {})
                                city = loc_dict.get("city", "")
                                country = loc_dict.get("country", "")
                                location = loc_dict.get("fullLocation") or f"{city}, {country}".strip(", ") or "Not specified"
                                job_id = p.get("id")
                                pub_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}"

                                detail_url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{job_id}"
                                det_req = urllib.request.Request(detail_url, headers={"User-Agent": "Mozilla/5.0"})
                                raw_desc = ""
                                try:
                                    with urllib.request.urlopen(det_req, timeout=8) as d_resp:
                                        d_data = json.loads(d_resp.read().decode("utf-8", errors="ignore"))
                                        sections = d_data.get("jobAd", {}).get("sections", {})
                                        raw_desc = " ".join([sec.get("text", "") for sec in sections.values() if isinstance(sec, dict)])
                                        pub_url = d_data.get("postingUrl") or pub_url
                                except Exception:
                                    pass

                                matches = extract_matched_keywords(f"{title} {raw_desc}")
                                if matches:
                                    exp_req = extract_experience(raw_desc)
                                    is_ind = is_india_location(location)
                                    cluster_k = make_job_cluster_key(c_name, title, location)
                                    job_entry = {
                                        "company": c_name,
                                        "title": title,
                                        "location": location,
                                        "job_url": pub_url,
                                        "experience": exp_req,
                                        "matched_keywords": matches,
                                        "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "source": "Career Site (SmartRecruiters)",
                                        "is_india": is_ind,
                                        "cluster_key": cluster_k,
                                        "application_links": [
                                            {"portal": "Direct Career Site", "url": pub_url}
                                        ]
                                    }
                                    comp_matches.append(job_entry)
                    except Exception:
                        pass

        return c_name, comp_k, comp_matches

    if tracker:
        tracker.set_stage(f"Phase 1: Scanning {len(all_companies)} enterprise career sites from #{start_cursor + 1}...", len(state["matched_jobs"]))

    companies_scanned_this_run = 0
    # Execute company career sites concurrently in cursor order
    with ThreadPoolExecutor(max_workers=12) as executor:
        future_to_comp = {executor.submit(fetch_company_postings, c): c for c in ordered_companies}
        for future in as_completed(future_to_comp):
            companies_scanned_this_run += 1
            if tracker and tracker.should_stop(len(state["matched_jobs"])):
                break
            elif len(state["matched_jobs"]) >= target_limit:
                break

            try:
                c_name, comp_key, all_company_matches = future.result()

                # Include ALL matching roles from the company, without suppressing non-India roles
                for job in all_company_matches:
                    if tracker and tracker.should_stop(len(state["matched_jobs"])):
                        break
                    elif len(state["matched_jobs"]) >= target_limit:
                        break
                    is_new = merge_or_append_job(state["matched_jobs"], job)
                    state["seen_job_urls"].append(job["job_url"])
                    if is_new:
                        added += 1
                        if tracker:
                            tracker.on_job_added(len(state["matched_jobs"]))
                        print(f"    [MATCH #{len(state['matched_jobs'])}] {job['company']} - {job['title']} [{job['experience']}] ({job['location']})")
                    else:
                        print(f"    [MERGED DUPLICATE] Added direct career link for: {job['company']} - {job['title']}")

                processed[comp_key] = {
                    "name": c_name,
                    "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": f"Found {len(all_company_matches)} matches" if all_company_matches else "Analyzed - No active matches",
                    "source": "Direct Enterprise Career Site"
                }
            except Exception as e:
                pass

    # Advance circular cursor persistently
    new_cursor = (start_cursor + companies_scanned_this_run) % max(1, total_companies)
    if start_cursor + companies_scanned_this_run >= total_companies:
        state["scan_cycle"] = current_cycle + 1
        print(f"[Career Site Queue] Completed Cycle {current_cycle}! Advancing to Cycle {state['scan_cycle']}.")
    state["company_cursor"] = new_cursor
    print(f"[Career Site Queue] Cursor advanced: Next run will start at Company #{new_cursor + 1}/{total_companies}.")

    save_state(state)
    generate_html_report(state)

    return added

def search_global_job_boards(target_limit: int, state: Dict, tracker: SessionTracker = None, skip_linkedin: bool = False, skip_indeed: bool = False, skip_glassdoor: bool = False) -> int:
    """
    Searches worldwide job aggregators ordered by the 4-tier relocation strategy:
    Priority 1: India
    Priority 2: Non-Schengen (USA, UK, Canada, Australia, NZ, Russia)
    Priority 3: Other Non-EU Global (Japan, etc.)
    Priority 4: Schengen EU (Germany, France, Sweden, etc. - Last Resort)
    """
    added = 0
    print("\n--- Phase 2: Global Job Boards (Indeed, Glassdoor, LinkedIn) ---")

    processed = state["processed_companies"]
    seen_urls = set(state.get("seen_job_urls", []))

    search_terms = ["Codebeamer", "\"PTC Integrity\"", "\"MKS Integrity\"", "Codebeamer ALM"]
    sites = []
    if not skip_indeed:
        sites.append("indeed")
    if not skip_glassdoor:
        sites.append("glassdoor")
    if not skip_linkedin:
        sites.append("linkedin")

    if not sites:
        print("[Global Boards] All aggregators skipped per user request.")
        return 0

    country_phases = [
        {"name": "Tier 1: India (Top Priority)", "countries": ["india"]},
        {"name": "Tier 2: Non-Schengen Global (High Interest)", "countries": ["usa", "uk", "canada", "australia"]},
        {"name": "Tier 3: Other Global Non-EU", "countries": ["japan"]},
        {"name": "Tier 4: Schengen EU (Last Resort)", "countries": ["germany", "france", "sweden"]}
    ]

    company_candidates: Dict[str, List[Dict]] = {}

    for phase in country_phases:
        if tracker and tracker.should_stop(len(state["matched_jobs"])):
            break
        elif len(state["matched_jobs"]) >= target_limit:
            break

        print(f"\nScanning Region: {phase['name']}...")
        for term in search_terms:
            if tracker and tracker.should_stop(len(state["matched_jobs"])):
                break
            elif len(state["matched_jobs"]) >= target_limit:
                break

            for country in phase["countries"]:
                if tracker and tracker.should_stop(len(state["matched_jobs"])):
                    break
                elif len(state["matched_jobs"]) >= target_limit:
                    break

                active_sites = [s for s in sites if not (s == "glassdoor" and country in ["sweden", "japan"])]

                if tracker:
                    tracker.set_stage(f"Phase 2: Scanning {country.upper()} for '{term}'...", len(state["matched_jobs"]))

                print(f"Searching '{term}' in {country.upper()}...")
                try:
                    jobs_df = scrape_jobs(
                        site_name=active_sites,
                        search_term=term,
                        results_wanted=35,
                        fetch_description=True,
                        country_indeed=country,
                        verbose=0
                    )

                    if jobs_df is None or jobs_df.empty:
                        continue

                    for _, row in jobs_df.iterrows():
                        raw_comp = row.get("company")
                        if not raw_comp or pd.isna(raw_comp):
                            continue

                        company_clean = clean_company_name(str(raw_comp))
                        comp_key = company_clean.lower()

                        job_url = str(row.get("job_url", "")).strip()
                        if not job_url or job_url in seen_urls:
                            continue

                        desc = str(row.get("description", ""))
                        title = str(row.get("title", "Unknown Role")).strip()
                        location = str(row.get("location", "")).strip()
                        if not location or location == "nan":
                            location = country.upper()

                        combined_text = f"{title}\n{desc}"
                        matched_kws = extract_matched_keywords(combined_text)

                        if matched_kws:
                            is_ind = is_india_location(location) or country.lower() == "india"
                            exp_req = extract_experience(desc)
                            portal_src = str(row.get("site", "Job Board")).title()
                            cluster_k = make_job_cluster_key(company_clean, title, location)

                            job_entry = {
                                "company": company_clean,
                                "title": title,
                                "location": location,
                                "job_url": job_url,
                                "experience": exp_req,
                                "matched_keywords": matched_kws,
                                "date_found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "source": portal_src,
                                "is_india": is_ind,
                                "cluster_key": cluster_k,
                                "application_links": [
                                    {"portal": portal_src, "url": job_url}
                                ]
                            }
                            seen_urls.add(job_url)

                            if comp_key not in company_candidates:
                                company_candidates[comp_key] = []
                            company_candidates[comp_key].append(job_entry)

                except Exception as e:
                    print(f"Error fetching {country} for {term}: {e}")
                    time.sleep(1)

        print(f"\nFlushing candidates from {phase['name']} to state and dashboard...")
        for comp_key, candidate_jobs in list(company_candidates.items()):
            if tracker and tracker.should_stop(len(state["matched_jobs"])):
                break
            elif len(state["matched_jobs"]) >= target_limit:
                break

            c_name = candidate_jobs[0]["company"]

            # List ALL matching roles from each company without discarding non-India roles
            comp_added = 0
            for job in candidate_jobs:
                if tracker and tracker.should_stop(len(state["matched_jobs"])):
                    break
                elif len(state["matched_jobs"]) >= target_limit:
                    break
                is_new = merge_or_append_job(state["matched_jobs"], job)
                state["seen_job_urls"].append(job["job_url"])
                if is_new:
                    added += 1
                    comp_added += 1
                    if tracker:
                        tracker.on_job_added(len(state["matched_jobs"]))
                    print(f"  [MATCH #{len(state['matched_jobs'])}/{target_limit}] {job['company']} - {job['title']} [{job['experience']}] ({job['location']})")
                else:
                    print(f"  [MERGED LINK] Consolidated cross-posted link for: {job['company']} - {job['title']}")

            processed[comp_key] = {
                "name": c_name,
                "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": f"Found {len(candidate_jobs)} matches" if candidate_jobs else "Analyzed - Keyword Verified",
                "source": candidate_jobs[0]["source"] if candidate_jobs else "Web/Aggregator"
            }

            del company_candidates[comp_key]
            save_state(state)
            generate_html_report(state)

    return added

def generate_html_report(state: Dict):
    """Renders a modern, interactive dual-tab HTML dashboard with status checkboxes, tiers, ATS score, best CV & certificates, and quick crawl trigger."""
    matched_jobs = state.get("matched_jobs", [])

    # Evaluate ATS scores for all jobs (both existing and newly added)
    if ATSManager:
        try:
            ats_mgr = ATSManager()
            for j in matched_jobs:
                # If not evaluated or if CVs/certs are available, evaluate
                eval_res = ats_mgr.evaluate_job(j)
                j["best_cv"] = eval_res["best_cv"]
                j["ats_score"] = eval_res["ats_score"]
                j["recommended_certificates"] = eval_res["recommended_certificates"]
        except Exception as e:
            print(f"[Warning] ATS Evaluation error: {e}")

    processed_companies = list(state.get("processed_companies", {}).values())
    last_updated = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

    processed_companies.sort(key=lambda x: x.get("name", "").lower())

    india_count = sum(1 for j in matched_jobs if classify_location_tier(j.get("location", ""))[0] == 1)
    non_schengen_count = sum(1 for j in matched_jobs if classify_location_tier(j.get("location", ""))[0] == 2)
    schengen_count = sum(1 for j in matched_jobs if classify_location_tier(j.get("location", ""))[0] == 4)

    job_rows_html = []
    for idx, job in enumerate(matched_jobs, 1):
        kws_badges = " ".join([f'<span class="badge badge-kw">{html.escape(k)}</span>' for k in job.get("matched_keywords", [])])
        loc = html.escape(str(job.get("location") or "Worldwide / Unspecified"))
        comp = html.escape(str(job.get("company", "")))
        title = html.escape(str(job.get("title", "")))
        date_found = html.escape(str(job.get("date_found", "")))
        source = html.escape(str(job.get("source", "Career Site")))
        exp = html.escape(str(job.get("experience", "Not Specified")))
        cluster_k = html.escape(str(job.get("cluster_key", f"job_{idx}")))

        tier_num, tier_label = classify_location_tier(job.get("location", ""))
        if tier_num == 1:
            tier_badge = '<span class="badge badge-tier-1">🇮🇳 Tier 1: India</span>'
        elif tier_num == 2:
            tier_badge = '<span class="badge badge-tier-2">🌏 Tier 2: Non-Schengen</span>'
        elif tier_num == 4:
            tier_badge = '<span class="badge badge-tier-4" title="Schengen/EU - Caution regarding German Pension waiting period">⚠️ Tier 4: Schengen</span>'
        else:
            tier_badge = '<span class="badge badge-tier-3">🌐 Tier 3: Global Non-EU</span>'

        if exp == "Not Specified":
            exp_badge = '<span class="badge badge-exp-na">Not Specified</span>'
        else:
            exp_badge = f'<span class="badge badge-exp">{exp}</span>'

        app_links = job.get("application_links", [])
        if not app_links:
            app_links = [{"portal": source, "url": job.get("job_url", "#")}]

        links_html = []
        for l_item in app_links:
            p_name = html.escape(str(l_item.get("portal", "Apply")))
            p_url = html.escape(str(l_item.get("url", "#")))
            btn_class = "btn-portal-direct" if "direct" in p_name.lower() or "workday" in p_name.lower() else "btn-portal"
            link_tag = f"""
            <a href="{p_url}" target="_blank" rel="noopener noreferrer" class="{btn_class}" title="Open posting on {p_name}">
                {p_name} <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
            </a>
            """
            links_html.append(link_tag)

        all_links_markup = f'<div class="links-container">{"".join(links_html)}</div>'

        best_cv_val = job.get("best_cv", "Add CV to /CV folder")
        ats_score_val = float(job.get("ats_score", 0.0))
        rec_certs = job.get("recommended_certificates", [])

        # Color-coded ATS Match Badge
        if ats_score_val >= 80:
            ats_badge = f'<span class="badge badge-ats-high" title="Strong ATS Match ({ats_score_val}%)">🟢 {ats_score_val}%</span>'
        elif ats_score_val >= 60:
            ats_badge = f'<span class="badge badge-ats-mid" title="Moderate ATS Match ({ats_score_val}%)">🟡 {ats_score_val}%</span>'
        elif ats_score_val > 0:
            ats_badge = f'<span class="badge badge-ats-low" title="Low ATS Match ({ats_score_val}%)">🔴 {ats_score_val}%</span>'
        else:
            ats_badge = '<span class="badge badge-exp-na" title="Drop CV files into /CV to compute ATS Match Score">N/A</span>'

        def clean_cv_name(raw_name: str) -> str:
            """Formats CV filename for clean display: e.g. Abhishek_Singh_CV_AI_Automation.pdf -> AI Automation"""
            base = os.path.splitext(raw_name)[0]
            # Strip standard prefix like Abhishek_Singh_CV_ or CV_
            base = re.sub(r'^(abhishek_singh_cv_|abhishek_singh_|cv_)', '', base, flags=re.IGNORECASE)
            return base.replace("_", " ").title()

        def clean_cert_name(raw_name: str) -> str:
            """Formats certificate filename cleanly: e.g. CertificateOfCompletion_Introduction to Disciplined Agile.pdf -> Intro to Disciplined Agile"""
            base = os.path.splitext(raw_name)[0]
            base = re.sub(r'^(certificateofcompletion_|certificate_of_completion_|certificate_)', '', base, flags=re.IGNORECASE)
            base = base.replace("Introduction to", "Intro to")
            return base.replace("_", " ").strip()

        # Best CV Badge with full clean label & hover tooltip
        if best_cv_val and best_cv_val != "Add CV to /CV folder":
            clean_cv = clean_cv_name(best_cv_val)
            cv_badge = f'<span class="badge badge-cv" title="Full File: {html.escape(best_cv_val)}">📄 {html.escape(clean_cv)}</span>'
        else:
            cv_badge = '<span class="badge badge-exp-na" title="No CV in /CV folder">📁 No CV</span>'

        # Certificates Badges with clean readable labels
        if rec_certs:
            certs_badges = " ".join([f'<span class="badge badge-cert" title="Full File: {html.escape(c)}">🎓 {html.escape(clean_cert_name(c))}</span>' for c in rec_certs])
        else:
            certs_badges = '<span class="badge badge-exp-na" title="Standard application">None required</span>'

        row = f"""
        <tr id="row-{cluster_k}" data-job-id="{cluster_k}" data-tier="{tier_num}" data-ats="{ats_score_val}">
            <td class="col-status">
                <label class="status-toggle" title="Check if you have applied for this job">
                    <input type="checkbox" id="chk-{cluster_k}" onchange="toggleJobStatus('{cluster_k}')">
                    <span class="custom-chk"></span>
                    <span class="status-label" id="lbl-{cluster_k}">To Apply</span>
                </label>
            </td>
            <td class="col-num">{idx}</td>
            <td class="col-comp"><strong>{comp}</strong></td>
            <td class="col-role">
                <div class="role-title">{title}</div>
                <div class="role-source">Indexed {date_found}</div>
            </td>
            <td class="col-ats">{ats_badge}</td>
            <td class="col-best-cv">{cv_badge}</td>
            <td class="col-certs">{certs_badges}</td>
            <td class="col-exp">{exp_badge}</td>
            <td class="col-loc">
                <div style="margin-bottom: 4px;">{tier_badge}</div>
                <span class="loc-text"><span class="loc-pin">📍</span> {loc}</span>
            </td>
            <td class="col-kws">{kws_badges}</td>
            <td class="col-action">{all_links_markup}</td>
        </tr>
        """
        job_rows_html.append(row)

    comp_rows_html = []
    for idx, comp in enumerate(processed_companies, 1):
        name = html.escape(str(comp.get("name", "")))
        status = html.escape(str(comp.get("status", "Analyzed")))
        checked_at = html.escape(str(comp.get("checked_at", "")))
        source = html.escape(str(comp.get("source", "Web/Portal")))
        status_class = "status-matched" if "match" in status.lower() and "no" not in status.lower() else "status-checked"

        crow = f"""
        <tr>
            <td class="col-num">{idx}</td>
            <td class="col-comp"><strong>{name}</strong></td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{source}</td>
            <td class="text-muted">{checked_at}</td>
        </tr>
        """
        comp_rows_html.append(crow)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global ALM Career Opportunities (Codebeamer | PTC Integrity | MKS Integrity)</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-body: #0d1117;
            --bg-card: #161b22;
            --border-color: #30363d;
            --text-main: #f0f6fc;
            --text-muted: #8b949e;
            --accent-blue: #2f81f7;
            --accent-green: #238636;
            --accent-purple: #a371f7;
            --accent-amber: #d29922;
            --hover-row: #1c2128;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.5;
            padding: 24px;
        }}

        .container {{
            max-width: 98%;
            width: 98%;
            margin: 0 auto;
        }}

        header {{
            background: linear-gradient(135deg, #161b22 0%, #1f242c 100%);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px 28px;
            margin-bottom: 24px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}

        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .crawler-toggles-bar {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            padding: 6px 14px;
            border-radius: 8px;
            flex-wrap: wrap;
        }}

        .toggle-chip {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 500;
            color: #c9d1d9;
            cursor: pointer;
            user-select: none;
        }}

        .toggle-chip input[type="checkbox"] {{
            cursor: pointer;
            width: 14px;
            height: 14px;
            accent-color: #f85149;
        }}

        h1 {{
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subtitle {{
            color: var(--text-muted);
            margin-top: 4px;
            font-size: 13px;
        }}

        .btn-crawl {{
            background: linear-gradient(135deg, #238636 0%, #2ea043 100%);
            color: #ffffff;
            border: 1px solid #3fb950;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(35, 134, 54, 0.3);
        }}

        .btn-crawl:hover {{
            background: #2ea043;
            transform: translateY(-1px);
        }}

        .btn-crawl:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        .metrics-bar {{
            display: flex;
            gap: 12px;
            margin-top: 18px;
            flex-wrap: wrap;
        }}

        .metric-card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 16px;
            display: flex;
            flex-direction: column;
        }}

        .metric-val {{
            font-size: 20px;
            font-weight: 700;
            color: var(--accent-blue);
        }}

        .metric-label {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .tabs-nav {{
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 20px;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 12px 18px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .tab-btn:hover {{
            color: var(--text-main);
        }}

        .tab-btn.active {{
            color: var(--accent-blue);
            border-bottom-color: var(--accent-blue);
        }}

        .tab-badge {{
            background: #21262d;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            color: var(--text-main);
        }}

        .tab-pane {{
            display: none;
        }}

        .tab-pane.active {{
            display: block;
        }}

        .controls-bar {{
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .search-input {{
            flex: 1;
            min-width: 250px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 10px 14px;
            color: var(--text-main);
            font-size: 14px;
            outline: none;
        }}

        .search-input:focus {{
            border-color: var(--accent-blue);
        }}

        .filter-btn-group {{
            display: flex;
            gap: 6px;
            align-items: center;
            flex-wrap: wrap;
        }}

        .filter-btn {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .filter-btn:hover {{
            color: var(--text-main);
            border-color: #8b949e;
        }}

        .filter-btn.active {{
            background: #21262d;
            color: var(--accent-blue);
            border-color: var(--accent-blue);
            font-weight: 600;
        }}

        .table-wrap {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow-x: auto;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 13px;
        }}

        th {{
            background: #1c2128;
            color: var(--text-muted);
            font-weight: 600;
            padding: 10px 10px;
            border-bottom: 1px solid var(--border-color);
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }}

        td {{
            padding: 10px 10px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}

        tbody tr:hover {{
            background-color: var(--hover-row);
        }}

        .col-status {{
            width: 85px;
            text-align: center;
        }}

        .status-toggle {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            user-select: none;
            padding: 4px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }}

        .status-toggle:hover {{
            border-color: #8b949e;
            background: rgba(255, 255, 255, 0.07);
        }}

        .status-toggle input[type="checkbox"] {{
            cursor: pointer;
            width: 15px;
            height: 15px;
            accent-color: var(--accent-green);
        }}

        .status-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: #8b949e;
        }}

        .row-applied {{
            background-color: rgba(35, 134, 54, 0.08) !important;
        }}

        .row-applied .status-label {{
            color: #7ee787;
        }}

        .col-num {{
            color: var(--text-muted);
            width: 38px;
            text-align: center;
        }}

        .col-comp {{
            font-size: 13.5px;
            color: #ffffff;
            min-width: 130px;
            max-width: 170px;
        }}

        .col-role {{
            min-width: 190px;
            max-width: 260px;
        }}

        .role-title {{
            font-weight: 600;
            color: #ffffff;
            font-size: 13px;
            line-height: 1.35;
        }}

        .role-source {{
            font-size: 10.5px;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        .col-exp {{
            min-width: 90px;
            white-space: nowrap;
        }}

        .col-loc {{
            min-width: 160px;
            max-width: 210px;
        }}

        .loc-text {{
            color: #c9d1d9;
            font-size: 12px;
            display: inline-block;
            line-height: 1.3;
        }}

        .loc-pin {{
            font-size: 11px;
            margin-right: 2px;
        }}

        .badge {{
            display: inline-block;
            padding: 3px 6px;
            border-radius: 5px;
            font-size: 11px;
            font-weight: 500;
            margin: 2px 2px;
        }}

        .badge-kw {{
            background: rgba(163, 113, 247, 0.15);
            color: #d2a8ff;
            border: 1px solid rgba(163, 113, 247, 0.35);
        }}

        .badge-tier-1 {{
            background: rgba(210, 153, 34, 0.15);
            color: #e3b341;
            border: 1px solid rgba(210, 153, 34, 0.4);
            font-weight: 600;
        }}

        .badge-tier-2 {{
            background: rgba(35, 134, 54, 0.15);
            color: #7ee787;
            border: 1px solid rgba(35, 134, 54, 0.4);
            font-weight: 600;
        }}

        .badge-tier-3 {{
            background: rgba(88, 166, 255, 0.12);
            color: #79c0ff;
            border: 1px solid rgba(88, 166, 255, 0.3);
        }}

        .badge-tier-4 {{
            background: rgba(248, 81, 73, 0.12);
            color: #ff7b72;
            border: 1px solid rgba(248, 81, 73, 0.3);
        }}

        .badge-exp {{
            background: rgba(56, 139, 253, 0.15);
            color: #58a6ff;
            border: 1px solid rgba(56, 139, 253, 0.35);
            font-weight: 600;
        }}

        .badge-exp-na {{
            background: rgba(110, 118, 129, 0.15);
            color: #8b949e;
            border: 1px solid rgba(110, 118, 129, 0.3);
            font-style: italic;
        }}

        .badge-ats-high {{
            background: rgba(46, 160, 67, 0.2);
            color: #3fb950;
            border: 1px solid rgba(46, 160, 67, 0.45);
            font-weight: 700;
            font-size: 11.5px;
            padding: 2px 7px;
            white-space: nowrap;
        }}

        .badge-ats-mid {{
            background: rgba(210, 153, 34, 0.2);
            color: #e3b341;
            border: 1px solid rgba(210, 153, 34, 0.45);
            font-weight: 700;
            font-size: 11.5px;
            padding: 2px 7px;
            white-space: nowrap;
        }}

        .badge-ats-low {{
            background: rgba(248, 81, 73, 0.15);
            color: #ff7b72;
            border: 1px solid rgba(248, 81, 73, 0.35);
            font-weight: 600;
            font-size: 11.5px;
            padding: 2px 7px;
            white-space: nowrap;
        }}

        .badge-cv {{
            background: rgba(56, 139, 253, 0.15);
            color: #79c0ff;
            border: 1px solid rgba(56, 139, 253, 0.35);
            font-weight: 600;
            display: inline-block;
            padding: 4px 8px;
            white-space: nowrap;
            vertical-align: middle;
            font-size: 11.5px;
        }}

        .badge-cert {{
            background: rgba(163, 113, 247, 0.18);
            color: #d2a8ff;
            border: 1px solid rgba(163, 113, 247, 0.4);
            font-weight: 500;
            display: inline-block;
            margin: 2px 2px;
            padding: 4px 8px;
            white-space: nowrap;
            vertical-align: middle;
            font-size: 11px;
        }}

        .col-ats {{
            width: 80px;
            text-align: center;
        }}

        .col-best-cv {{
            min-width: 140px;
            white-space: nowrap;
        }}

        .col-certs {{
            min-width: 160px;
        }}

        .col-kws {{
            min-width: 100px;
        }}

        .col-action {{
            min-width: 140px;
        }}

        .links-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            align-items: center;
        }}

        .btn-portal-direct {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: var(--accent-green);
            color: #ffffff;
            padding: 5px 9px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 11.5px;
            font-weight: 600;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .btn-portal-direct:hover {{
            background: #2ea043;
            transform: translateY(-1px);
        }}

        .btn-portal {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid var(--border-color);
            padding: 5px 9px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 11.5px;
            font-weight: 500;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .btn-portal:hover {{
            background: #30363d;
            color: #ffffff;
            border-color: #8b949e;
            transform: translateY(-1px);
        }}

        .doc-box {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 24px;
            line-height: 1.6;
            margin-bottom: 24px;
        }}

        .doc-box h2 {{
            font-size: 18px;
            color: #ffffff;
            margin-bottom: 12px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }}

        .doc-box h3 {{
            font-size: 15px;
            color: var(--accent-blue);
            margin: 16px 0 6px 0;
        }}

        .doc-box ul {{
            padding-left: 20px;
            color: #c9d1d9;
            font-size: 14px;
        }}

        .doc-box li {{
            margin-bottom: 6px;
        }}

        .doc-box code {{
            background: #21262d;
            padding: 2px 6px;
            border-radius: 4px;
            color: #79c0ff;
            font-size: 13px;
        }}

        /* Live Graphical Progress Bar */
        .progress-card {{
            display: none;
            background: linear-gradient(135deg, rgba(22, 27, 34, 0.98) 0%, rgba(29, 35, 43, 0.98) 100%);
            border: 1px solid rgba(47, 129, 247, 0.45);
            border-radius: 12px;
            padding: 18px 22px;
            margin-bottom: 22px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
            animation: fadeIn 0.3s ease;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(-6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .progress-top-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .progress-status-info {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .pulsing-dot {{
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background-color: #2ea043;
            box-shadow: 0 0 10px #2ea043;
            animation: pulse-dot 1.3s infinite ease-in-out;
            flex-shrink: 0;
        }}

        @keyframes pulse-dot {{
            0%, 100% {{ transform: scale(1); opacity: 1; box-shadow: 0 0 6px #2ea043; }}
            50% {{ transform: scale(1.3); opacity: 0.7; box-shadow: 0 0 18px #58a6ff; }}
        }}

        .progress-title-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .progress-title-row strong {{
            font-size: 15px;
            color: #ffffff;
            letter-spacing: -0.2px;
        }}

        .progress-target-badge {{
            background: rgba(88, 166, 255, 0.15);
            border: 1px solid rgba(88, 166, 255, 0.35);
            color: #58a6ff;
            font-size: 12px;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 16px;
        }}

        .progress-subtitle {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 3px;
        }}

        .progress-percentage-badge {{
            font-size: 22px;
            font-weight: 800;
            color: #58a6ff;
            font-family: monospace;
            background: rgba(255, 255, 255, 0.05);
            padding: 4px 14px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .progress-track {{
            width: 100%;
            height: 14px;
            background: #21262d;
            border-radius: 7px;
            overflow: hidden;
            position: relative;
            border: 1px solid #30363d;
        }}

        .progress-fill {{
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #2f81f7 0%, #2ea043 55%, #3fb950 100%);
            border-radius: 7px;
            transition: width 0.4s ease;
            position: relative;
            background-size: 28px 28px;
            background-image: linear-gradient(
                135deg,
                rgba(255, 255, 255, 0.18) 25%,
                transparent 25%,
                transparent 50%,
                rgba(255, 255, 255, 0.18) 50%,
                rgba(255, 255, 255, 0.18) 75%,
                transparent 75%,
                transparent
            );
            animation: progress-stripes 1.2s linear infinite;
        }}

        @keyframes progress-stripes {{
            0% {{ background-position: 0 0; }}
            100% {{ background-position: 28px 0; }}
        }}

        .progress-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 10px;
            font-size: 12px;
            color: var(--text-muted);
            flex-wrap: wrap;
            gap: 8px;
        }}

        .spinner {{
            width: 14px;
            height: 14px;
            border: 2px solid #58a6ff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <div>
                    <h1>💼 Global ALM Opportunity Dashboard</h1>
                    <div class="subtitle">Keyword-verified career openings mentioning <strong>Codebeamer</strong>, <strong>PTC Integrity</strong>, or <strong>MKS Integrity</strong></div>
                </div>
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <!-- Skip Aggregators Checkbox Bar -->
                    <div class="crawler-toggles-bar" title="Avoid 429 Too Many Requests by skipping aggregators on frequent runs">
                        <span style="font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase;">Skip Sources:</span>
                        <label class="toggle-chip" title="Check to skip LinkedIn search (prevents 429 rate limit)">
                            <input type="checkbox" id="skipLinkedinChk">
                            <span>Skip LinkedIn</span>
                        </label>
                        <label class="toggle-chip" title="Check to skip Naukri search">
                            <input type="checkbox" id="skipNaukriChk">
                            <span>Skip Naukri</span>
                        </label>
                        <label class="toggle-chip" title="Check to skip Indeed search">
                            <input type="checkbox" id="skipIndeedChk">
                            <span>Skip Indeed</span>
                        </label>
                        <label class="toggle-chip" title="Check to skip Glassdoor search">
                            <input type="checkbox" id="skipGlassdoorChk">
                            <span>Skip Glassdoor</span>
                        </label>
                    </div>

                    <button class="btn-crawl" id="crawlBtn" onclick="triggerWebCrawl()">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        <span>Crawl New Openings</span>
                    </button>
                    <div style="color: var(--text-muted); font-size: 12px;">Last Updated: {last_updated}</div>
                </div>
            </div>

            <div class="metrics-bar">
                <div class="metric-card">
                    <span class="metric-val">{len(matched_jobs)}</span>
                    <span class="metric-label">Distinct Job Postings</span>
                </div>
                <div class="metric-card">
                    <span class="metric-val" style="color: #7ee787;" id="appliedCount">0</span>
                    <span class="metric-label">✅ Applied Jobs</span>
                </div>
                <div class="metric-card">
                    <span class="metric-val" style="color: #e3b341;">{india_count}</span>
                    <span class="metric-label">🇮🇳 Tier 1: India</span>
                </div>
                <div class="metric-card">
                    <span class="metric-val" style="color: #7ee787;">{non_schengen_count}</span>
                    <span class="metric-label">🌏 Tier 2: Non-Schengen</span>
                </div>
                <div class="metric-card">
                    <span class="metric-val" style="color: #ff7b72;">{schengen_count}</span>
                    <span class="metric-label">⚠️ Tier 4: Schengen</span>
                </div>
                <div class="metric-card">
                    <span class="metric-val" style="color: #8b949e;">{len(processed_companies)}</span>
                    <span class="metric-label">Companies Evaluated</span>
                </div>
            </div>
        </header>

        <!-- Live Graphical Progress Card -->
        <div id="liveProgressCard" class="progress-card">
            <div class="progress-top-row">
                <div class="progress-status-info">
                    <span class="pulsing-dot" id="progressPulse"></span>
                    <div>
                        <div class="progress-title-row">
                            <strong id="progressStage">Ready to Crawl</strong>
                            <span class="progress-target-badge" id="progressNewCounter">0 / 50 New Openings Found</span>
                        </div>
                        <div class="progress-subtitle" id="progressDetail">Evaluating live portals across India &amp; global tech hubs...</div>
                    </div>
                </div>
                <div class="progress-percentage-badge" id="progressPercentBadge">0%</div>
            </div>

            <div class="progress-track">
                <div class="progress-fill" id="progressBarFill" style="width: 0%;"></div>
            </div>

            <div class="progress-footer">
                <span id="progressHeartbeat">🟢 Process Health: Idle / Monitoring</span>
                <span id="progressNotice">Auto-stops after 50 new jobs • Zero duplicate company-roles</span>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="tabs-nav">
            <button class="tab-btn active" onclick="switchTab('tab-jobs', this)">
                🎯 Matched Job Openings <span class="tab-badge">{len(matched_jobs)}</span>
            </button>
            <button class="tab-btn" onclick="switchTab('tab-companies', this)">
                🏢 Evaluated Companies <span class="tab-badge">{len(processed_companies)}</span>
            </button>
            <button class="tab-btn" onclick="switchTab('tab-guide', this)">
                📖 How to Use & Relocation Guide
            </button>
        </div>

        <!-- Tab 1: Matched Jobs -->
        <div id="tab-jobs" class="tab-pane active">
            <div class="controls-bar">
                <input type="text" id="jobSearch" class="search-input" placeholder="🔍 Search by company, role, experience, location, or keyword..." onkeyup="applyFilters()">
                <div class="filter-btn-group">
                    <button class="filter-btn active" onclick="setStatusFilter('all', this)">All Statuses</button>
                    <button class="filter-btn" onclick="setStatusFilter('to_apply', this)">To Apply</button>
                    <button class="filter-btn" onclick="setStatusFilter('applied', this)">Applied Only</button>
                </div>
                <div class="filter-btn-group">
                    <button class="filter-btn active" onclick="setTierFilter('all', this)">All Regions</button>
                    <button class="filter-btn" onclick="setTierFilter('1', this)">🇮🇳 India (Tier 1)</button>
                    <button class="filter-btn" onclick="setTierFilter('2', this)">🌏 Non-Schengen (Tier 2)</button>
                    <button class="filter-btn" onclick="setTierFilter('4', this)">⚠️ Schengen (Tier 4)</button>
                </div>
                <div class="filter-btn-group">
                    <button class="filter-btn active" onclick="setAtsFilter('all', this)">All ATS</button>
                    <button class="filter-btn" onclick="setAtsFilter('high', this)">🟢 80%+ Match</button>
                    <button class="filter-btn" onclick="setAtsFilter('mid', this)">🟡 60%+ Match</button>
                </div>
            </div>
            <div class="table-wrap">
                <table id="jobsTable">
                    <thead>
                        <tr>
                            <th class="col-status">Status</th>
                            <th class="col-num">#</th>
                            <th>Company Name</th>
                            <th>Job Role</th>
                            <th class="col-ats">ATS Match</th>
                            <th class="col-best-cv">Best CV</th>
                            <th class="col-certs">Certificates to Attach</th>
                            <th>Experience</th>
                            <th>Location / Tier</th>
                            <th>Matched Criteria</th>
                            <th>Application Links</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(job_rows_html) if job_rows_html else '<tr><td colspan="11" class="empty-state">No matching job postings found yet.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 2: Processed Companies -->
        <div id="tab-companies" class="tab-pane">
            <div class="controls-bar">
                <input type="text" id="compSearch" class="search-input" placeholder="🔍 Search evaluated companies..." onkeyup="filterTable('compTable', this.value)">
            </div>
            <div class="table-wrap">
                <table id="compTable">
                    <thead>
                        <tr>
                            <th class="col-num">#</th>
                            <th>Company Name</th>
                            <th>Audit Status</th>
                            <th>Source / Portal</th>
                            <th>Date Evaluated</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(comp_rows_html) if comp_rows_html else '<tr><td colspan="5" class="empty-state">No companies recorded in history yet.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Tab 3: Documentation & Guide -->
        <div id="tab-guide" class="tab-pane">
            <div class="doc-box">
                <h2>📖 ALM Career Search & Relocation Guide</h2>
                
                <h3>1. Geographical Hierarchy Strategy (German Pension Protection)</h3>
                <p style="color: #c9d1d9; margin-bottom: 10px;">To ensure your 5-year German Pension contributions refund remains intact, you must observe a 24-month waiting period without mandatory German/EU social security coverage. This portal organizes postings accordingly:</p>
                <ul>
                    <li><strong style="color: #e3b341;">🇮🇳 Tier 1 (India)</strong>: Top focus for the next 2 years. Roles in Bengaluru, Hyderabad, Pune, Gurugram, etc., with medical and automotive giants.</li>
                    <li><strong style="color: #7ee787;">🌏 Tier 2 (Non-Schengen Global)</strong>: USA, UK, Canada, Australia, New Zealand, Russia, UAE. These countries carry no conflict with German pension claim timelines.</li>
                    <li><strong style="color: #79c0ff;">🌐 Tier 3 (Global Other)</strong>: International remote or non-EU markets (Japan, Singapore, etc.).</li>
                    <li><strong style="color: #ff7b72;">⚠️ Tier 4 (Schengen / EU)</strong>: Germany, France, Sweden, etc. Flagged as last resort to safeguard your pension refund eligibility.</li>
                </ul>

                <h3>2. Tracking Your Applications</h3>
                <ul>
                    <li>Click the checkbox on any job row to mark it as <code style="color: #7ee787;">Applied</code>.</li>
                    <li>Your applied history is saved automatically in your browser's persistent storage. You will never lose your progress even if the crawler pulls new openings.</li>
                    <li>Use the <strong>"To Apply"</strong> filter to hide positions you've already finished applying to.</li>
                </ul>

                <h3>3. Multi-Portal Links</h3>
                <ul>
                    <li>When companies cross-post jobs across multiple job sites, all application channels are grouped together on a single row (e.g. <code>Workday Direct</code>, <code>Indeed</code>, <code>Glassdoor</code>, <code>Naukri</code>).</li>
                    <li>Direct enterprise links (green buttons) bypass recruiter agency filters and take you straight to the internal career requisition.</li>
                </ul>

                <h3>4. Running Crawls Automatically</h3>
                <ul>
                    <li>You can click the green <strong>"Crawl New Openings"</strong> button at the top of the web app anytime to fetch fresh listings.</li>
                    <li>Or launch the local server in your terminal: <code>python app_server.py</code> and access your dashboard at <code>http://localhost:5000</code>.</li>
                </ul>
            </div>
        </div>
    </div>

    <script>
        const STORAGE_KEY = 'alm_applied_jobs_v1';
        let currentStatusFilter = 'all';
        let currentTierFilter = 'all';
        let currentAtsFilter = 'all';

        function getAppliedJobs() {{
            try {{
                return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            }} catch (e) {{
                return [];
            }}
        }}

        function saveAppliedJobs(list) {{
            localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
        }}

        function toggleJobStatus(jobId) {{
            let applied = getAppliedJobs();
            const chk = document.getElementById('chk-' + jobId);
            const lbl = document.getElementById('lbl-' + jobId);
            const row = document.getElementById('row-' + jobId);

            if (chk.checked) {{
                if (!applied.includes(jobId)) applied.push(jobId);
                lbl.innerText = 'Applied';
                if (row) row.classList.add('row-applied');
            }} else {{
                applied = applied.filter(id => id !== jobId);
                lbl.innerText = 'To Apply';
                if (row) row.classList.remove('row-applied');
            }}

            saveAppliedJobs(applied);
            updateAppliedCount();
            applyFilters();
        }}

        function updateAppliedCount() {{
            const applied = getAppliedJobs();
            const counter = document.getElementById('appliedCount');
            if (counter) counter.innerText = applied.length;
        }}

        function restoreAppliedState() {{
            const applied = getAppliedJobs();
            applied.forEach(jobId => {{
                const chk = document.getElementById('chk-' + jobId);
                const lbl = document.getElementById('lbl-' + jobId);
                const row = document.getElementById('row-' + jobId);
                if (chk) chk.checked = true;
                if (lbl) lbl.innerText = 'Applied';
                if (row) row.classList.add('row-applied');
            }});
            updateAppliedCount();
        }}

        function setStatusFilter(filterType, btn) {{
            currentStatusFilter = filterType;
            btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function setTierFilter(tierType, btn) {{
            currentTierFilter = tierType;
            btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function setAtsFilter(atsType, btn) {{
            currentAtsFilter = atsType;
            btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function applyFilters() {{
            const query = (document.getElementById('jobSearch')?.value || '').toLowerCase();
            const rows = document.querySelectorAll('#jobsTable tbody tr');
            const applied = getAppliedJobs();

            rows.forEach(row => {{
                const jobId = row.getAttribute('data-job-id');
                const rowTier = row.getAttribute('data-tier');
                const rowAts = parseFloat(row.getAttribute('data-ats') || '0');
                const isApplied = jobId ? applied.includes(jobId) : false;
                const text = row.innerText.toLowerCase();

                let matchesSearch = text.includes(query);
                let matchesStatus = true;
                let matchesTier = true;
                let matchesAts = true;

                if (currentStatusFilter === 'applied') {{
                    matchesStatus = isApplied;
                }} else if (currentStatusFilter === 'to_apply') {{
                    matchesStatus = !isApplied;
                }}

                if (currentTierFilter !== 'all') {{
                    matchesTier = (rowTier === currentTierFilter);
                }}

                if (currentAtsFilter === 'high') {{
                    matchesAts = (rowAts >= 80.0);
                }} else if (currentAtsFilter === 'mid') {{
                    matchesAts = (rowAts >= 60.0);
                }}

                row.style.display = (matchesSearch && matchesStatus && matchesTier && matchesAts) ? '' : 'none';
            }});
        }}

        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }}

        function filterTable(tableId, query) {{
            const filter = query.toLowerCase();
            const rows = document.querySelectorAll('#' + tableId + ' tbody tr');
            rows.forEach(row => {{
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            }});
        }}

        let wasCrawlingBefore = false;

        function pollCrawlStatus() {{
            fetch('/api/status', {{ cache: 'no-store' }})
                .then(r => r.json())
                .then(data => {{
                    const btn = document.getElementById('crawlBtn');
                    const card = document.getElementById('liveProgressCard');
                    const stageEl = document.getElementById('progressStage');
                    const detailEl = document.getElementById('progressDetail');
                    const counterEl = document.getElementById('progressNewCounter');
                    const percentEl = document.getElementById('progressPercentBadge');
                    const fillEl = document.getElementById('progressBarFill');
                    const heartbeatEl = document.getElementById('progressHeartbeat');
                    const pulseEl = document.getElementById('progressPulse');

                    if (!card) return;

                    if (data && data.is_crawling) {{
                        wasCrawlingBefore = true;
                        card.style.display = 'block';
                        if (btn) {{
                            btn.disabled = true;
                            btn.style.opacity = '0.7';
                            btn.innerHTML = `<span class="spinner"></span> <span>Crawling (${{data.new_found || 0}}/${{data.target_new || 50}})...</span>`;
                        }}

                        if (stageEl) stageEl.innerText = data.stage || 'Crawling job portals in background...';
                        if (detailEl) detailEl.innerText = `Current database total: ${{data.total_jobs || 0}} distinct roles.`;
                        const targetNew = data.target_new || 50;
                        const found = data.new_found || 0;
                        if (counterEl) counterEl.innerText = `${{found}} / ${{targetNew}} New Openings Found`;

                        const pct = (data.percent !== undefined) ? data.percent : Math.min(100, Math.round((found / Math.max(1, targetNew)) * 100));
                        if (percentEl) percentEl.innerText = `${{pct}}%`;
                        if (fillEl) fillEl.style.width = `${{pct}}%`;
                        if (heartbeatEl) heartbeatEl.innerHTML = `🟢 Process Health: Active &amp; Running (Updated: ${{data.updated_at || 'Live'}})`;
                        if (pulseEl) pulseEl.style.backgroundColor = '#2ea043';
                    }} else {{
                        if (btn) {{
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> <span>Crawl New Openings</span>`;
                        }}

                        if (wasCrawlingBefore) {{
                            wasCrawlingBefore = false;
                            card.style.display = 'block';
                            if (stageEl) stageEl.innerText = '✅ Session Complete! 50 new openings reached.';
                            if (counterEl) counterEl.innerText = '50 / 50 New Openings Found';
                            if (percentEl) percentEl.innerText = '100%';
                            if (fillEl) fillEl.style.width = '100%';
                            if (heartbeatEl) heartbeatEl.innerHTML = '🏁 Target reached normally. Reloading fresh openings...';
                            if (pulseEl) pulseEl.style.backgroundColor = '#58a6ff';
                            setTimeout(() => {{ window.location.reload(); }}, 2000);
                        }}
                    }}
                }})
                .catch(() => {{
                    // Fallback when viewing directly via file://
                }});
        }}

        function triggerWebCrawl() {{
            const btn = document.getElementById('crawlBtn');
            const card = document.getElementById('liveProgressCard');
            const stageEl = document.getElementById('progressStage');
            const fillEl = document.getElementById('progressBarFill');
            const percentEl = document.getElementById('progressPercentBadge');

            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = `<span class="spinner"></span> <span>Starting Crawl...</span>`;
            }}
            if (card) card.style.display = 'block';
            if (stageEl) stageEl.innerText = 'Initializing crawler (Naukri India, Workday, Aggregators)...';
            if (fillEl) fillEl.style.width = '2%';
            if (percentEl) percentEl.innerText = '0%';

            const skipLinkedin = document.getElementById('skipLinkedinChk')?.checked || false;
            const skipNaukri = document.getElementById('skipNaukriChk')?.checked || false;
            const skipIndeed = document.getElementById('skipIndeedChk')?.checked || false;
            const skipGlassdoor = document.getElementById('skipGlassdoorChk')?.checked || false;

            const payload = {{
                skip_linkedin: skipLinkedin,
                skip_naukri: skipNaukri,
                skip_indeed: skipIndeed,
                skip_glassdoor: skipGlassdoor
            }};

            fetch('/api/crawl', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }})
                .then(r => r.json())
                .then(data => {{
                    pollCrawlStatus();
                }})
                .catch(err => {{
                    if (stageEl) stageEl.innerText = 'Server not running on localhost:5000. Start app_server.py to enable 1-click crawling directly from browser.';
                    setTimeout(() => {{
                        if (btn) btn.disabled = false;
                    }}, 4000);
                }});
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            restoreAppliedState();
            pollCrawlStatus();
            setInterval(pollCrawlStatus, 1500);
        }});
    </script>
</body>
</html>
"""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n[Dashboard Updated] HTML report generated at: {REPORT_FILE}")

def main():
    parser = argparse.ArgumentParser(description="Global ALM Job Crawler")
    parser.add_argument("--target", type=int, default=150, help="Target total number of distinct matching jobs")
    parser.add_argument("--new-limit", type=int, default=50, help="Stop after finding this many brand-new openings in this session")
    parser.add_argument("--clear-cache", action="store_true", help="Wipe existing cache and restart from scratch")
    parser.add_argument("--continuous", action="store_true", help="Search exhaustively without stopping at target count")
    parser.add_argument("--evaluate-ats", action="store_true", help="Re-evaluate ATS scores and best CV/certs for all jobs in database and update dashboard")
    parser.add_argument("--skip-naukri", action="store_true", help="Skip Naukri.com scraper to avoid rate limits")
    parser.add_argument("--skip-linkedin", action="store_true", help="Skip LinkedIn aggregator to avoid HTTP 429 errors")
    parser.add_argument("--skip-indeed", action="store_true", help="Skip Indeed aggregator")
    parser.add_argument("--skip-glassdoor", action="store_true", help="Skip Glassdoor aggregator")
    args = parser.parse_args()

    if args.clear_cache:
        print("[Notice] --clear-cache specified. Wiping previous state...")
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    state = load_state()

    if args.evaluate_ats:
        print("=== Re-evaluating ATS Scores & Best CV Matching for all stored jobs ===")
        if ATSManager:
            ats_mgr = ATSManager()
            ats_mgr.refresh()
            print(f"Found {len(ats_mgr.cv_profiles)} CVs and {len(ats_mgr.cert_profiles)} certificates.")
            updated_cnt = ats_mgr.evaluate_all_jobs(state.get("matched_jobs", []))
            save_state(state)
            generate_html_report(state)
            print(f"[Done] Successfully evaluated ATS scores and updated report for {updated_cnt} jobs.")
        else:
            print("[Error] ATSManager could not be imported.")
        return
    current_count = len(state.get("matched_jobs", []))
    session_new_limit = 0 if args.continuous else args.new_limit
    if args.continuous:
        target_count = 999999
    elif session_new_limit > 0:
        target_count = current_count + session_new_limit
    else:
        target_count = args.target

    tracker = SessionTracker(target_total=target_count, new_limit=session_new_limit)
    tracker.save_progress(current_count, is_running=True)

    print(f"=== Starting Global ALM Job Crawler (Tiered Relocation Strategy) ===")
    print(f"Session Target: Stop after {session_new_limit} NEW openings found" if session_new_limit > 0 else f"Target Total Jobs: {target_count}")
    print(f"Currently saved matches in database: {current_count}")
    print(f"Previously reviewed companies: {len(state.get('processed_companies', {}))}")

    # Career-First Execution Hierarchy:
    # 1. Direct Enterprise Career Sites run FIRST to prioritize direct applications
    print("\n--- Phase 1: Direct Enterprise Career Sites (Top Priority) ---")
    search_workday_careers(target_count, state, tracker)

    # 2. If target not reached, engage Naukri and Global Boards concurrently
    if not tracker.should_stop(len(state["matched_jobs"])):
        print("\n--- Phase 2: Supplementary Discovery (Naukri & Global Boards) ---")
        threads = []
        if not getattr(args, "skip_naukri", False):
            threads.append(threading.Thread(target=lambda: search_naukri_career_portal(target_count, state, tracker), name="Agent-Naukri"))
        else:
            print("[Info] Skipping Naukri.com as requested.")

        threads.append(threading.Thread(target=lambda: search_global_job_boards(
            target_count, state, tracker,
            skip_linkedin=getattr(args, "skip_linkedin", False),
            skip_indeed=getattr(args, "skip_indeed", False),
            skip_glassdoor=getattr(args, "skip_glassdoor", False)
        ), name="Agent-Global"))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

    tracker.save_progress(len(state["matched_jobs"]), is_running=False)
    generate_html_report(state)
    print(f"\nCrawler completed. Session added: {tracker.newly_added} new jobs. Total matches collected: {len(state['matched_jobs'])}")

if __name__ == "__main__":
    main()
