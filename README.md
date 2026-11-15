# 🚀 JobCrawlerForFree: Automated Enterprise Job Crawler & ATS Optimization Engine

An intelligent, multi-threaded career crawling and ATS optimization platform engineered for technical professionals and job seekers. It searches across **enterprise corporate career portals (Workday, Greenhouse, Lever, SmartRecruiters)** and major job aggregators (**Naukri, Indeed, Glassdoor, LinkedIn**), automatically deduplicates postings, scores each job against your resumes, and suggests which CV and certificates to submit.

---

## 🌟 Why This Project?

Most commercial job search tools are behind paywalls, heavily rate-limited, or flood you with sponsored and duplicate listings.

**JobCrawlerForFree** gives you:
1. **Direct Enterprise Career Site Priority**: Direct integration with corporate ATS APIs (Workday, Greenhouse, Lever, SmartRecruiters) so you bypass third-party aggregators whenever direct career endpoints are available.
2. **Automated ATS Resume Matcher**: Parses your PDF/DOCX resumes and computes an ATS match percentage (0–100%) for every single job found.
3. **Smart Certificate Mapper**: Inspects your credentials and tells you exactly which certificates to attach to maximize interview callbacks.
4. **Interactive Dashboard**: A sleek, dark-mode web application (running locally at `http://localhost:5000`) with:
   - 1-click crawling
   - Source skip toggles (`Skip LinkedIn`, `Skip Naukri`, `Skip Indeed`, `Skip Glassdoor`) to prevent 429 rate limits
   - Persistent application status tracking (`To Apply` vs `Applied` saved to your browser)
   - Clean, non-congested badge view with direct application links.

---

## 🏗️ Architecture & How It Works

```
                                +---------------------------+
                                |  Target Datasets & Lists  |
                                |  (S&P 500, Tech Lists)    |
                                +-------------+-------------+
                                              |
                                              v
                                +---------------------------+
                                |    ATS Company Prober     |
                                |  (Workday, GH, Lever, SR) |
                                +-------------+-------------+
                                              |
                                              v
                                      companies.json
                                              |
                                              v
+-------------------------+      +---------------------------+      +--------------------------+
| Direct Career Endpoints | ---> |     ALM Job Crawler       | <--- | External Aggregators     |
| (Multi-Threaded APIs)   |      |  (alm_job_crawler.py)     |      | (Naukri, Indeed, etc.)   |
+-------------------------+      +-------------+-------------+      +--------------------------+
                                              |
                                              v
                                +---------------------------+
                                |      ATS Match Engine     | <--- User CVs & Certificates
                                |     (ats_engine.py)       |      (/CV & /certificates)
                                +-------------+-------------+
                                              |
                                              v
                                +---------------------------+
                                |  Local Web Dashboard      |
                                |  (http://localhost:5000)  |
                                +---------------------------+
```

---

## 📂 Repository Structure

```
JobCrawlerForFree/
├── .gitignore                          # Clean repository setup (excludes large raw datasets and secrets)
├── playwright_bot/
│   ├── alm_job_crawler.py              # Main crawler engine (multi-threaded, circular pointer, ATS engine)
│   ├── app_server.py                   # Local Flask web dashboard server (http://localhost:5000)
│   ├── ats_company_prober.py           # Auto-discovers and tests company ATS endpoints
│   ├── ats_engine.py                   # Resume parser, ATS scoring engine & certificate recommender
│   ├── companies.json                  # Verified directory of enterprise career portals
│   ├── crawler_state.json              # Persistent crawler state (cursor index, cycle count, job database)
│   ├── ingest_and_merge_datasets.py    # Merges external company lists and probes live ATS endpoints
│   ├── get_sp500.py                    # Script to pull live S&P 500 enterprise companies
│   ├── matched_jobs_report.html        # Interactive, dark-mode dashboard UI template
│   ├── naukri_scraper.py               # Targeted scraper for Indian tech job boards
│   ├── CV/                             # Place your personal resumes (PDF/DOCX) here
│   ├── certificates/                   # Place your certificates (PDF) here
│   └── Additional_CSV_Datasets/        # Processed datasets and indexes
└── USER_MANUAL.md                      # Comprehensive step-by-step user guide
```

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.10+ installed
- Git installed
- Google Chrome installed (for Playwright scraping)

### 2. Clone the Repository
```bash
git clone https://github.com/abhi2k67/JobCrawlerForFree.git
cd JobCrawlerForFree/playwright_bot
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

pip install flask playwright beautifulsoup4 pypdf python-docx requests
playwright install chromium
```

### 4. Add Your Resumes & Certifications
- Copy your PDF or DOCX resumes into `playwright_bot/CV/`.
- Copy your credentials or certificates into `playwright_bot/certificates/`.

### 5. Launch the Dashboard
```bash
python app_server.py
```
Open your browser and navigate to:
👉 **[http://localhost:5000](http://localhost:5000)**

---

## 🛠️ How to Customize for Your Domain

This repository is pre-configured for **ALM / Software Engineering** (Codebeamer, PTC Integrity, Requirements Management, Embedded & Systems Engineering), but you can easily adapt it for **any industry**:

1. **Change Keywords**: Open `playwright_bot/alm_job_crawler.py` and modify `SEARCH_QUERIES`:
   ```python
   SEARCH_QUERIES = [
       "DevOps Engineer",
       "Kubernetes",
       "Cloud Architect"
   ]
   ```
2. **Customize Target Companies**: Add target organizations directly into `playwright_bot/companies.json` or run `ats_company_prober.py` with your custom list.
3. **Adjust Geographical Priorities**: Modify the country and tier dictionaries in `alm_job_crawler.py` to match your local market or relocation strategy.

---

## 📖 Documentation
For full instructions, troubleshooting, and advanced dataset ingestion, read the [USER_MANUAL.md](file:///d:/Automation/USER_MANUAL.md).

---

## ⚖️ License & Disclaimer
This project is for educational and personal career automation purposes. Ensure you comply with the terms of service of each platform you crawl.
