"""
ALM Career Portal Local Server:
Runs a lightweight web server on http://localhost:5000 so you can:
1. View the dashboard directly in your browser.
2. Click the 'Crawl New Openings' button on the dashboard to trigger background runs without terminal commands.
3. Automatically refresh and update results live.
"""

import os
import sys
import json
import threading
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_FILE = os.path.join(BASE_DIR, "matched_jobs_report.html")
PYTHON_EXE = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

PROGRESS_FILE = os.path.join(BASE_DIR, "crawler_progress.json")
crawl_lock = threading.Lock()
is_crawling = False

def run_crawler_process(skip_flags: dict = None):
    global is_crawling
    with crawl_lock:
        is_crawling = True
        try:
            cmd = [PYTHON_EXE, os.path.join(BASE_DIR, "alm_job_crawler.py"), "--new-limit", "50"]
            if skip_flags:
                if skip_flags.get("skip_naukri"):
                    cmd.append("--skip-naukri")
                if skip_flags.get("skip_linkedin"):
                    cmd.append("--skip-linkedin")
                if skip_flags.get("skip_indeed"):
                    cmd.append("--skip-indeed")
                if skip_flags.get("skip_glassdoor"):
                    cmd.append("--skip-glassdoor")

            print(f"[Server] Launching background crawler: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=BASE_DIR, check=False)
            print("[Server] Crawler process finished.")
        except Exception as e:
            print(f"[Server Error] Crawler execution error: {e}")
        finally:
            is_crawling = False
            # Update progress file state
            if os.path.exists(PROGRESS_FILE):
                try:
                    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                        p_data = json.load(f)
                    p_data["is_running"] = False
                    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                        json.dump(p_data, f, indent=2)
                except Exception:
                    pass

class ALMDashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html", "/dashboard"):
            if os.path.exists(REPORT_FILE):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                with open(REPORT_FILE, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"matched_jobs_report.html not found.")
                return

        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            status_payload = {
                "is_crawling": is_crawling,
                "stage": "Idle",
                "new_found": 0,
                "target_new": 50,
                "total_jobs": 0,
                "percent": 0,
                "updated_at": ""
            }

            if os.path.exists(PROGRESS_FILE):
                try:
                    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                        disk_p = json.load(f)
                        status_payload.update(disk_p)
                except Exception:
                    pass

            # Server's live lock status takes precedence
            status_payload["is_crawling"] = is_crawling
            self.wfile.write(json.dumps(status_payload).encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        global is_crawling
        if self.path == "/api/crawl":
            if is_crawling:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "running", "message": "Crawler is already active in background."}).encode("utf-8"))
                return

            # Read optional JSON body for skip flags
            skip_flags = {}
            try:
                content_len = int(self.headers.get('Content-Length', 0))
                if content_len > 0:
                    post_data = self.rfile.read(content_len)
                    skip_flags = json.loads(post_data.decode('utf-8'))
            except Exception:
                pass

            t = threading.Thread(target=run_crawler_process, args=(skip_flags,), daemon=True)
            t.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "message": "Crawl triggered successfully! Refreshing dashboard in a few seconds."}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_server(port=5000):
    os.chdir(BASE_DIR)
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, ALMDashboardHandler)
    print(f"\n=======================================================")
    print(f"[ALM Dashboard Server] Running at: http://localhost:{port}")
    print(f"=======================================================")
    print("Keep this terminal open or run it as a background service.")
    print("Press Ctrl+C to stop the server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    run_server(5000)
