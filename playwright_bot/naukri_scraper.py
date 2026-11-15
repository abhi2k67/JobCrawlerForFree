"""
Naukri.com Automated Job Search Engine for ALM Tools:
Targets: 'Codebeamer', 'PTC Integrity', 'MKS Integrity'

Uses Playwright with anti-detection flags to extract real-time job listings from Naukri India.
"""

import time
import re
from typing import List, Dict
from playwright.sync_api import sync_playwright

NAUKRI_KEYWORDS = [
    {"term": "Codebeamer", "slug": "codebeamer-jobs"},
    {"term": "PTC Integrity", "slug": "ptc-integrity-jobs"},
    {"term": "MKS Integrity", "slug": "mks-integrity-jobs"}
]

def scrape_naukri_jobs(max_pages_per_keyword: int = 2) -> List[Dict]:
    """
    Scrapes Naukri India job listings for ALM keywords using Playwright.
    Returns list of parsed job candidate dictionaries.
    """
    collected_jobs = []
    seen_urls = set()

    print("\n--- Phase 0: India Tech Jobs Engine (Naukri.com) ---")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-infobars',
                    '--window-position=0,0',
                    '--window-size=1280,800'
                ]
            )
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            for item in NAUKRI_KEYWORDS:
                term = item["term"]
                slug = item["slug"]
                print(f"Searching Naukri for '{term}'...")

                for page_no in range(1, max_pages_per_keyword + 1):
                    url = f"https://www.naukri.com/{slug}-{page_no}" if page_no > 1 else f"https://www.naukri.com/{slug}"
                    try:
                        page.goto(url, timeout=25000)
                        page.wait_for_timeout(3000)

                        tuples = page.locator('.srp-jobtuple-wrapper')
                        count = tuples.count()
                        if count == 0:
                            break

                        print(f"  Page {page_no}: Found {count} listings on Naukri.")

                        for i in range(count):
                            t = tuples.nth(i)
                            try:
                                title_elem = t.locator('.title')
                                title = title_elem.inner_text().strip()
                                job_url = title_elem.get_attribute('href')
                                if not job_url:
                                    continue
                                job_url = job_url.split('?')[0] # clean query tracking params

                                if job_url in seen_urls:
                                    continue
                                seen_urls.add(job_url)

                                comp_elem = t.locator('.comp-name')
                                comp = comp_elem.inner_text().strip() if comp_elem.count() > 0 else "Unknown Company"

                                exp_elem = t.locator('.exp-wrap')
                                exp_str = exp_elem.inner_text().strip() if exp_elem.count() > 0 else "Not Specified"
                                if exp_str != "Not Specified" and not exp_str.lower().endswith("yrs") and not exp_str.lower().endswith("years"):
                                    exp_str = f"{exp_str} Yrs"

                                loc_elem = t.locator('.loc-wrap')
                                loc_str = loc_elem.inner_text().strip() if loc_elem.count() > 0 else "India"

                                desc_elem = t.locator('.job-desc')
                                desc_snippet = desc_elem.inner_text().strip() if desc_elem.count() > 0 else ""

                                collected_jobs.append({
                                    "company": comp,
                                    "title": title,
                                    "location": f"{loc_str}, India" if "india" not in loc_str.lower() else loc_str,
                                    "job_url": job_url,
                                    "experience": exp_str,
                                    "matched_keywords": [term],
                                    "source": "Naukri",
                                    "description": f"{title}\n{desc_snippet}\n{term}",
                                    "is_india": True
                                })
                            except Exception:
                                continue

                        # If less than 20 results, this was the last page
                        if count < 20:
                            break

                    except Exception as e:
                        print(f"  Warning on Naukri {term} page {page_no}: {e}")
                        break

            browser.close()

    except Exception as e:
        print(f"Naukri scraping note: {e}")

    print(f"Naukri scan finished: Retrieved {len(collected_jobs)} India candidate roles.\n")
    return collected_jobs

if __name__ == "__main__":
    jobs = scrape_naukri_jobs(1)
    for j in jobs[:5]:
        print(f"- {j['title']} | {j['company']} | {j['experience']} | {j['location']}")
