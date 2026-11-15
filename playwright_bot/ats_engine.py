"""
ATS Matching & Evaluation Engine for ALM Job Crawler.

Handles:
1. Extraction of text from multiple document formats (.pdf, .docx, .txt, .md).
2. Parsing all CVs in the 'CV' directory and certificates in 'certificates'.
3. Extracting skills, certifications, keywords, and domain relevance.
4. Calculating ATS Match Score (0 - 100%) against job titles, keywords, requirements, and descriptions.
5. Determining the best CV and relevant matching certificates for each job opening.
"""

import os
import re
import math
from typing import Dict, List, Tuple, Any

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import docx
except ImportError:
    docx = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CV_DIR = os.path.join(BASE_DIR, "CV")
CERT_DIR = os.path.join(BASE_DIR, "certificates")

# Core ALM, technical, and engineering skill vocabulary for ATS analysis
TECHNICAL_TERMS = {
    # ALM & PLM Tools
    "codebeamer", "ptc integrity", "mks integrity", "polarion", "jira", "confluence",
    "doors", "doors next generation", "dng", "windchill", "teamcenter", "alm", "plm",
    # Scripting & Languages
    "python", "java", "javascript", "typescript", "c++", "c#", ".net", "sql", "bash", "shell", "powershell",
    "groovy", "rest api", "soap", "json", "xml",
    # DevOps & CI/CD
    "git", "github", "gitlab", "bitbucket", "jenkins", "docker", "kubernetes", "ci/cd", "azure devops", "ansible",
    # Practices & Methodologies
    "agile", "scrum", "kanban", "waterfall", "sdlc", "devops", "aspice", "iso 26262", "iec 62304",
    "functional safety", "system engineering", "requirements engineering", "test management",
    "validation", "verification", "traceability", "change management"
}

def extract_text_from_file(file_path: str) -> str:
    """Extracts raw text from .pdf, .docx, .txt, or .md file."""
    if not os.path.exists(file_path):
        return ""
    
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    
    try:
        if ext == ".txt" or ext == ".md":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == ".pdf":
            if pdfplumber:
                with pdfplumber.open(file_path) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            pages_text.append(extracted)
                    text = "\n".join(pages_text)
            else:
                try:
                    from pdfminer.high_level import extract_text as pdfminer_extract
                    text = pdfminer_extract(file_path)
                except Exception:
                    pass
        elif ext in (".docx", ".doc"):
            if docx and ext == ".docx":
                doc = docx.Document(file_path)
                text = "\n".join([p.text for p in doc.paragraphs if p.text])
    except Exception as e:
        print(f"[ATS Parser Warning] Could not extract text from {file_path}: {e}")
    
    return text.strip()

def tokenize_and_clean(text: str) -> List[str]:
    """Tokenizes text into lowercase words, stripping non-alphanumeric chars."""
    if not text:
        return []
    cleaned = re.sub(r'[^a-zA-Z0-9+#\.]', ' ', text.lower())
    words = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
    return words

class DocumentProfile:
    def __init__(self, filename: str, filepath: str, text: str):
        self.filename = filename
        self.filepath = filepath
        self.text = text
        self.text_lower = text.lower()
        self.tokens = set(tokenize_and_clean(text))
        
        # Detect present technical terms
        self.skills = set()
        for term in TECHNICAL_TERMS:
            if " " in term:
                if re.search(r'\b' + re.escape(term) + r'\b', self.text_lower):
                    self.skills.add(term)
            else:
                if term in self.tokens:
                    self.skills.add(term)

def load_cv_profiles(cv_folder: str = CV_DIR) -> List[DocumentProfile]:
    """Loads and caches profiles of all CV files."""
    profiles = []
    if not os.path.exists(cv_folder):
        return profiles
    
    valid_exts = {".pdf", ".docx", ".doc", ".txt", ".md"}
    for f in os.listdir(cv_folder):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_exts and not f.startswith("~$") and not f.lower().startswith("readme"):
            full_path = os.path.join(cv_folder, f)
            text = extract_text_from_file(full_path)
            if text:
                profiles.append(DocumentProfile(f, full_path, text))
    return profiles

def load_certificate_profiles(cert_folder: str = CERT_DIR) -> List[DocumentProfile]:
    """Loads and caches profiles of all Certificate files."""
    profiles = []
    if not os.path.exists(cert_folder):
        return profiles
    
    valid_exts = {".pdf", ".docx", ".doc", ".txt", ".md"}
    for f in os.listdir(cert_folder):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_exts and not f.startswith("~$") and not f.lower().startswith("readme"):
            full_path = os.path.join(cert_folder, f)
            text = extract_text_from_file(full_path)
            # Even if text extraction is sparse (e.g. image certificate in pdf), we still profile the filename
            fallback_text = text if text else os.path.splitext(f)[0].replace("_", " ").replace("-", " ")
            profiles.append(DocumentProfile(f, full_path, fallback_text))
    return profiles

def calculate_ats_match(cv: DocumentProfile, job: Dict[str, Any]) -> float:
    """
    Computes ATS match percentage (0 - 100) between a CV and a job posting.
    
    Components:
    1. Mandatory ALM Target Match (Codebeamer, PTC Integrity, MKS Integrity) - 30% weight
    2. Job Title Keyword Alignment - 30% weight
    3. Technical Skills & Methodology Overlap - 25% weight
    4. Experience Level / Domain Compatibility - 15% weight
    """
    if not cv.text:
        return 0.0

    score = 0.0
    
    # 1. Target Keywords Match (Codebeamer, PTC Integrity, etc.)
    matched_kws = job.get("matched_keywords", [])
    if matched_kws:
        kw_hits = 0
        for kw in matched_kws:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', cv.text_lower):
                kw_hits += 1
        kw_ratio = kw_hits / len(matched_kws)
        score += kw_ratio * 30.0
    else:
        # Check against target keywords in general
        target_hits = sum(1 for kw in ["codebeamer", "ptc integrity", "mks integrity"] if kw in cv.text_lower)
        score += min(30.0, target_hits * 15.0)

    # 2. Job Title Alignment
    title = str(job.get("title", "")).lower()
    title_words = [w for w in re.sub(r'[^a-zA-Z0-9]', ' ', title).split() if len(w) > 2 and w not in {
        "senior", "lead", "engineer", "developer", "specialist", "consultant", "manager", "staff", "associate"
    }]
    if title_words:
        title_hits = sum(1 for w in title_words if w in cv.tokens or w in cv.text_lower)
        score += (title_hits / len(title_words)) * 30.0
    else:
        score += 20.0  # neutral credit if title has only generic words

    # 3. Technical Skills & Methodology Overlap
    # Check what skills the job description / title emphasizes
    job_text = (str(job.get("title", "")) + " " + " ".join(matched_kws) + " " + str(job.get("description", ""))).lower()
    job_skills = set()
    for term in TECHNICAL_TERMS:
        if " " in term:
            if re.search(r'\b' + re.escape(term) + r'\b', job_text):
                job_skills.add(term)
        else:
            if term in job_text:
                job_skills.add(term)
    
    if job_skills:
        skill_hits = len(job_skills.intersection(cv.skills))
        score += min(25.0, (skill_hits / max(1, len(job_skills))) * 25.0)
    else:
        # Fallback to CV's rich ALM/tech skill density
        score += min(25.0, len(cv.skills) * 3.0)

    # 4. Experience & Domain Match
    exp_req = str(job.get("experience", "")).lower()
    if exp_req and exp_req != "not specified":
        exp_m = re.search(r'(\d+)', exp_req)
        if exp_m:
            req_yrs = int(exp_m.group(1))
            # Scan CV for experience years mentions
            cv_yrs_matches = [int(x) for x in re.findall(r'\b(\d{1,2})\+?\s*(?:years|yrs)\b', cv.text_lower)]
            max_cv_yrs = max(cv_yrs_matches) if cv_yrs_matches else 5
            if max_cv_yrs >= req_yrs:
                score += 15.0
            else:
                score += max(5.0, 15.0 - (req_yrs - max_cv_yrs) * 3.0)
        else:
            score += 12.0
    else:
        score += 12.0

    # Ensure score falls nicely within 10% - 98% realistic ATS band
    final_score = round(max(10.0, min(98.0, score)), 1)
    return final_score

def find_relevant_certificates(job: Dict[str, Any], cert_profiles: List[DocumentProfile]) -> List[str]:
    """Finds certificates matching the job's title, keywords, or domain."""
    if not cert_profiles:
        return []

    job_text = (str(job.get("title", "")) + " " + " ".join(job.get("matched_keywords", [])) + " " + str(job.get("description", ""))).lower()
    job_tokens = set(tokenize_and_clean(job_text))

    relevant_certs = []

    for cert in cert_profiles:
        # Check cert filename and content against job text
        cert_name_clean = os.path.splitext(cert.filename)[0].replace("_", " ").replace("-", " ").lower()
        cert_tokens = set(tokenize_and_clean(cert_name_clean)).union(cert.tokens)
        
        # Key domain associations
        is_match = False
        
        # 1. Direct keyword match
        common = job_tokens.intersection(cert_tokens)
        meaningful_common = [w for w in common if w not in {"certificate", "certification", "completed", "course", "certified", "of", "and", "in", "to", "for"}]
        if len(meaningful_common) >= 1:
            is_match = True

        # 2. Domain associations
        if any(w in job_text for w in ["agile", "scrum", "product owner", "sprint"]) and any(w in cert_name_clean for w in ["scrum", "agile", "csm", "psm", "pmp"]):
            is_match = True
        if any(w in job_text for w in ["aws", "cloud", "azure", "devops"]) and any(w in cert_name_clean for w in ["aws", "azure", "cloud", "devops", "kubernetes"]):
            is_match = True
        if any(w in job_text for w in ["codebeamer", "ptc", "integrity", "alm", "doors"]) and any(w in cert_name_clean for w in ["codebeamer", "ptc", "integrity", "alm", "requirements"]):
            is_match = True
        if any(w in job_text for w in ["test", "qa", "validation", "verification"]) and any(w in cert_name_clean for w in ["istqb", "testing", "quality", "qa"]):
            is_match = True
        if any(w in job_text for w in ["aspice", "automotive", "iso 26262"]) and any(w in cert_name_clean for w in ["aspice", "safety", "automotive", "26262"]):
            is_match = True

        if is_match:
            relevant_certs.append(cert.filename)

    return relevant_certs

class ATSManager:
    """Singleton-style coordinator to evaluate jobs against CVs and Certificates."""
    def __init__(self, cv_dir: str = CV_DIR, cert_dir: str = CERT_DIR):
        self.cv_dir = cv_dir
        self.cert_dir = cert_dir
        self.cv_profiles = load_cv_profiles(cv_dir)
        self.cert_profiles = load_certificate_profiles(cert_dir)

    def refresh(self):
        """Reloads CVs and certificates from disk."""
        self.cv_profiles = load_cv_profiles(self.cv_dir)
        self.cert_profiles = load_certificate_profiles(self.cert_dir)

    def evaluate_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a single job against all available CVs and certificates.
        Returns a dict with:
        - best_cv: str (filename)
        - ats_score: float (percentage)
        - recommended_certificates: List[str]
        """
        if not self.cv_profiles:
            # When user hasn't added CV files yet
            return {
                "best_cv": "Add CV to /CV folder",
                "ats_score": 0.0,
                "recommended_certificates": []
            }

        best_cv_profile = None
        best_score = -1.0

        for cv in self.cv_profiles:
            score = calculate_ats_match(cv, job)
            if score > best_score:
                best_score = score
                best_cv_profile = cv

        rec_certs = find_relevant_certificates(job, self.cert_profiles)

        return {
            "best_cv": best_cv_profile.filename if best_cv_profile else "N/A",
            "ats_score": best_score if best_score >= 0 else 0.0,
            "recommended_certificates": rec_certs
        }

    def evaluate_all_jobs(self, jobs: List[Dict[str, Any]]) -> int:
        """Evaluates and updates in-place all jobs in the list. Returns count updated."""
        count = 0
        for job in jobs:
            res = self.evaluate_job(job)
            job["best_cv"] = res["best_cv"]
            job["ats_score"] = res["ats_score"]
            job["recommended_certificates"] = res["recommended_certificates"]
            count += 1
        return count
