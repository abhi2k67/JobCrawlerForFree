from jobspy import scrape_jobs
import pandas as pd

print("Starting job search for Bengaluru...")

# Scrape jobs directly without any API keys or paid subscriptions
jobs = scrape_jobs(
    site_name=["linkedin", "indeed", "glassdoor"],
    search_term="Software Engineer",
    location="Bengaluru, Karnataka, India",
    results_wanted=30,
    hours_old=72,  # Fresh postings from the last 3 days
    country_ind="IN"
)

print(f"Found {len(jobs)} jobs successfully!")

# Save the results to a clean CSV file
output_file = "bengaluru_jobs.csv"
jobs.to_csv(output_file, index=False, encoding="utf-8")

print(f"Jobs saved successfully to {output_file}!")