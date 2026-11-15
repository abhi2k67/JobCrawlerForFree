# 💼 Global ALM Opportunity Dashboard & Crawler

Automated career opportunity search engine specialized for **Application Lifecycle Management (ALM)** tools:
- **Codebeamer**
- **PTC Integrity**
- **MKS Integrity**

Tailored specifically for an **India-first relocation strategy** and **German Pension (Deutsche Rentenversicherung) waiting period compliance**.

---

## 🧭 Geographical Hierarchy (Relocation & Pension Strategy)

Under German social security law, requesting a **refund of your 5-year German pension contributions** requires a **mandatory 24-month waiting period** during which you must not be subject to compulsory German/EU/Schengen social insurance contributions.

This platform categorizes all opportunities into four clear tiers:

| Tier | Badge | Target Countries | Strategy |
| :--- | :--- | :--- | :--- |
| **Tier 1** | 🇮🇳 `India` | Bengaluru, Hyderabad, Pune, Gurugram, Chennai, Noida, etc. | **Top Priority** for your 2-year tenure. High concentration of medical & automotive engineering hubs. |
| **Tier 2** | 🌏 `Non-Schengen` | USA, UK, Australia, Canada, New Zealand, Russia, UAE | **High Interest**. Major tech markets with zero conflict with your German pension refund. |
| **Tier 3** | 🌐 `Global Non-EU` | Japan, Singapore, Brazil, etc. | **Alternative Global Markets** / International relocation. |
| **Tier 4** | ⚠️ `Schengen (Last Resort)`| Germany, France, Sweden, Netherlands, Italy, etc. | **Last Resort Only**. Flagged with a warning to protect your pension claim window. |

---

## ⚡ Key Features

1. **Naukri.com Automated Engine**:
   - Uses Playwright with anti-bot bypass to crawl real-time job requisitions directly from India's #1 tech portal.
2. **Direct Enterprise Career Portals**:
   - Queries internal Workday REST APIs for medical device and automotive leaders (Medtronic, Stryker, Philips, Abbott, Boston Scientific, Baxter, ZF, Continental, Valeo, Magna, Honeywell, etc.).
3. **Global Job Aggregators**:
   - Scrapes Indeed, Glassdoor, and LinkedIn across priority countries worldwide.
4. **Cross-Platform Deduplication & Link Consolidation**:
   - Unifies company variations (e.g., `Bosch` vs `Bosch Group`, `EDAG` vs `EDAG Engineering`).
   - Merges identical cross-posted jobs into a single row with multi-portal application links (`[Workday Direct]`, `[Indeed]`, `[Glassdoor]`, `[Naukri]`).
5. **Experience Requirement Extraction**:
   - Analyzes descriptions to determine minimum/maximum tenure (e.g. `8+ Yrs`, `5 - 7 Yrs`). Resolves multi-skill mentions by taking the highest tenure.
6. **Application Status Tracking**:
   - Interactive checkboxes on every row to mark jobs as `Applied`.
   - Data is stored in your browser's persistent `localStorage` (`alm_applied_jobs_v1`). Re-crawling will **never delete or reset your applied checkboxes**.
7. **1-Click Crawling from Webapp**:
   - Trigger scans right from the HTML dashboard with a single click — no terminal required.

8. **Automated ATS Scoring & Best CV Recommendation**:
   - Compares every job opening (title, domain, skills, keywords, and tenure) against all resumes placed in the `CV/` folder.
   - Automatically selects the **Best CV** for that role and calculates a color-coded **ATS Match Score** (0–100%).
9. **Recommended Certificates Mapping**:
   - Scans all certifications placed in the `certificates/` folder and specifies which credentials (e.g. Scrum Master, AWS Cloud, Codebeamer Specialist, ASPICE, ISTQB) you should attach to each application.

---

## 📁 Folders for Your Documents

- **`d:\Automation\playwright_bot\CV\`**: Place all your CV / Resume variations here (supports `.pdf`, `.docx`, `.txt`, `.md`).
- **`d:\Automation\playwright_bot\certificates\`**: Place all your certificates here (supports `.pdf`, `.docx`, `.txt`, `.md`).

Whenever you add or update your CVs or certificates, you can instantly re-evaluate all jobs in your database by running:
```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/alm_job_crawler.py --evaluate-ats
```
Or start a new crawl via the web app (`http://localhost:5000`), which automatically updates all ATS scores upon generation.

---

## 🚀 How to Use

### Method 1: Interactive Web App (Recommended)

Run the local dashboard server in your virtual environment:

```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/app_server.py
```

Open your browser to:
👉 **[http://localhost:5000](http://localhost:5000)**

- Click the green **`Crawl New Openings`** button at the top right anytime you want to search.
- **50 New Openings Stop Condition**: Every run automatically scans across India & global tech hubs until **50 brand-new distinct job openings** are collected and appended, then gracefully stops.
- **Live Graphical Progress Bar**: A real-time progress card with an animated progress bar, percentage indicator, stage reporting (e.g. Workday portal, Naukri India, aggregators), and a pulsing health heartbeat assures you that the crawler is actively working.
- **Zero Repetition Guarantee**: Companies and roles you have already seen or applied for (e.g. Medtronic) are never duplicated as new rows. Cross-posted listings from other portals are consolidated into additional Apply buttons on the existing row, keeping your `Applied` checkboxes permanently intact.
- Filter by status (`All`, `To Apply`, `Applied Only`) or region tier (`India`, `Non-Schengen`, `Schengen`).

---

### Method 2: Command-Line Execution

To run crawls directly from your command line:

#### 1. Search for 50 new openings (Default Session Limit):
```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/alm_job_crawler.py --new-limit 50
```

#### 2. Search without limits (Continuous / All Jobs):
```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/alm_job_crawler.py --continuous
```

#### 3. Search for a specific total count (e.g., 250 jobs total):
```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/alm_job_crawler.py --target 250
```

#### 4. Fresh Start (Wipe cache):
```powershell
& "d:/Automation/playwright_bot/.venv/Scripts/python.exe" d:/Automation/playwright_bot/alm_job_crawler.py --clear-cache --new-limit 50
```

---

## 📁 Project Files

- **`alm_job_crawler.py`**: Core scraping and clustering pipeline.
- **`naukri_scraper.py`**: Dedicated Playwright scraper for Naukri India.
- **`app_server.py`**: Web server providing 1-click crawling from your browser at `http://localhost:5000`.
- **`matched_jobs_report.html`**: Dual-tab dashboard with search, filters, and documentation.
- **`crawler_state.json`**: State file maintaining reviewed companies, verified job URLs, and clustering keys.
