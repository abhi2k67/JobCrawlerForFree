# 📘 JobCrawlerForFree: Complete User Manual & Adaptation Guide

Welcome to the **JobCrawlerForFree** user manual. This guide is designed to help any job seeker configure, adapt, and run this automated career crawling and ATS optimization tool for their own career goals.

---

## Table of Contents
1. [Overview & Concept](#1-overview--concept)
2. [Folder & File Layout](#2-folder--file-layout)
3. [Installation & Setup](#3-installation--setup)
4. [Setting Up Your Profile (Resumes & Certifications)](#4-setting-up-your-profile-resumes--certifications)
5. [Running the Application](#5-running-the-application)
6. [Adapting for Your Domain (Tech, Data, Finance, Healthcare)](#6-adapting-for-your-domain)
7. [Expanding the Target Company List](#7-expanding-the-target-company-list)
8. [Dashboard Features & Source Skipping](#8-dashboard-features--source-skipping)
9. [Troubleshooting & Common FAQs](#9-troubleshooting--common-faqs)

---

## 1. Overview & Concept

JobCrawlerForFree operates on three core principles:
1. **Direct Enterprise Career Portals First**: It queries corporate Applicant Tracking Systems (ATS) directly—specifically **Workday**, **Greenhouse**, **Lever**, and **SmartRecruiters**. This gives you direct application links without middleman aggregators.
2. **Aggregator Fallback**: It can also query aggregators like Naukri, Indeed, Glassdoor, and LinkedIn.
3. **Automated ATS Scoring & Matching**: For every job found, the built-in ATS engine reads your local resumes in `/CV/`, extracts skills, keywords, and experience, compares them against the job description, and outputs:
   - A color-coded **ATS Match Score** (e.g. `92%`).
   - The **Best CV** from your folder to submit.
   - Specific **Certificates** to attach.

---

## 2. Folder & File Layout

```
JobCrawlerForFree/
├── .gitignore
├── README.md                      # GitHub homepage documentation
├── USER_MANUAL.md                 # This manual
└── playwright_bot/
    ├── alm_job_crawler.py         # Main crawling engine
    ├── app_server.py              # Flask server powering the UI
    ├── ats_company_prober.py      # Probes live ATS endpoints for any company name
    ├── ats_engine.py              # PDF/text resume parser & match calculator
    ├── companies.json             # Directory of enterprise career portals
    ├── crawler_state.json         # Stores all crawled openings and pointer state
    ├── matched_jobs_report.html   # Modern widescreen UI template
    ├── CV/                        # Put your CVs here (PDF/DOCX)
    └── certificates/              # Put your certificates here (PDF)
```

---

## 3. Installation & Setup

### Step 1: Install Python
Ensure Python 3.10 or higher is installed on your machine with `pip`.

### Step 2: Clone or Download the Repository
```bash
git clone https://github.com/abhi2k67/JobCrawlerForFree.git
cd JobCrawlerForFree/playwright_bot
```

### Step 3: Setup Virtual Environment & Dependencies
```bash
# Create environment
python -m venv .venv

# Activate environment:
# On Windows PowerShell:
.\.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

# Install required packages:
pip install flask playwright beautifulsoup4 pypdf python-docx requests

# Install the browser binary for Playwright:
playwright install chromium
```

---

## 4. Setting Up Your Profile (Resumes & Certifications)

The tool automatically analyzes your credentials against every job description:

1. **Add Your Resumes**:
   - Go to `playwright_bot/CV/`.
   - Delete the sample resumes and place your own resumes (`.pdf` or `.docx`).
   - *Tip:* If you have different specializations (e.g., `Resume_Frontend.pdf`, `Resume_FullStack.pdf`, `Resume_Manager.pdf`), add them all. The engine will pick the best one for each individual opening.

2. **Add Your Certifications**:
   - Go to `playwright_bot/certificates/`.
   - Place your relevant certificates (e.g., AWS, PMP, Scrum Master, Azure, ISTQB) as PDF files.
   - When a job mentions required skills matching any certificate, the dashboard highlights that certificate badge.

---

## 5. Running the Application

### Starting the Web Dashboard
From inside the `playwright_bot/` directory:
```powershell
python app_server.py
```
Or with full path:
```powershell
& "d:\Automation\playwright_bot\.venv\Scripts\python.exe" d:\Automation\playwright_bot\app_server.py
```

Open your browser to:
👉 **[http://localhost:5000](http://localhost:5000)**

Click **"Crawl New Openings"** on the dashboard. The system will crawl the target companies, process openings, update `crawler_state.json`, and refresh the table.

---

## 6. Adapting for Your Domain

By default, the crawler is set up for **ALM / Systems Engineering / Automotive Tech**. You can easily configure it for **Data Science, Web Development, DevOps, Healthcare, or Finance**:

### Step 1: Change Search Keywords
Open [`playwright_bot/alm_job_crawler.py`](file:///d:/Automation/playwright_bot/alm_job_crawler.py) in any editor:
Find the keyword list near the top:
```python
# Change these to your domain keywords:
SEARCH_QUERIES = [
    "Machine Learning Engineer",
    "Data Scientist",
    "NLP",
    "Computer Vision"
]
```

### Step 2: Customize ATS Engine Skills
Open [`playwright_bot/ats_engine.py`](file:///d:/Automation/playwright_bot/ats_engine.py):
Update the domain skill sets (e.g., programming languages, frameworks, or tools relevant to your field) so that the ATS scoring accurately reflects your industry.

---

## 7. Expanding the Target Company List

`companies.json` contains verified direct career portal endpoints.

### Adding New Companies Manually
To add a company using **Greenhouse**, **Lever**, or **SmartRecruiters**:
Open `playwright_bot/companies.json` and add:
```json
{
  "name": "Stripe",
  "ats": "greenhouse",
  "token": "stripe",
  "category": "Fintech"
}
```

### Auto-Probing Companies from Any List
You can use `ats_company_prober.py` to automatically check if a list of companies has active ATS endpoints:
```python
from ats_company_prober import bulk_probe_from_list, merge_into_companies_json

target_companies = ["Canva", "Brex", "DoorDash", "MongoDB", "Datadog"]
results = bulk_probe_from_list(target_companies)
merge_into_companies_json(results)
```
This automatically tests Greenhouse, Lever, and SmartRecruiters APIs and appends valid endpoints to `companies.json`.

---

## 8. Dashboard Features & Source Skipping

### Skip Toggles (Preventing Rate Limits & Duplicates)
At the top of the dashboard, you have four checkboxes:
- ☑️ `Skip LinkedIn`
- ☑️ `Skip Naukri`
- ☑️ `Skip Indeed`
- ☑️ `Skip Glassdoor`

**When to check them:**
- **Aggregators (LinkedIn/Indeed/Glassdoor)** often trigger `429 Too Many Requests` or return repeated job postings if crawled multiple times a day.
- **Recommended Workflow**: Keep all 4 **checked** for normal runs so the crawler runs at lightning speed against corporate career sites. Uncheck an aggregator only once per day for a broader scan.

### Persistent Application Tracking
- Each job row has an interactive status button (`To Apply` / `Applied`).
- When you click it, the status is saved to your browser's persistent `localStorage`.
- Running new crawls will **never** overwrite or reset your checkboxes.

---

## 9. Troubleshooting & Common FAQs

### Q: Why did a crawl add 0 new jobs?
1. If all 4 skip checkboxes are ticked, the crawler only looks at `companies.json`.
2. If all companies in `companies.json` were already scanned in the current cycle and no new jobs were posted by them today, it will wait for the next cycle or for new companies to be added.
3. *Solution:* Either uncheck an aggregator (e.g., Naukri or Indeed) or run `ingest_and_merge_datasets.py` to add more target companies to `companies.json`.

### Q: Can I run the crawler purely from the command line without the web browser?
Yes! Simply run:
```powershell
python alm_job_crawler.py --new-limit 50 --skip-linkedin
```

### Q: Where are the crawled jobs saved?
All indexed jobs are saved in `playwright_bot/crawler_state.json`. You can inspect this file or export it as needed.

---

*Happy Job Hunting! May this tool save you hundreds of hours of manual searching.*
