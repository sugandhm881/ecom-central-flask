import schedule
import time
import subprocess
from datetime import datetime, timedelta

# Track last run times to enforce 2-hour difference
last_run = {
    "data_fetcher": None,
    "cron_job": None
}

def can_run(job_name):
    """Ensure 2-hour gap between runs."""
    last_time = last_run.get(job_name)
    if last_time is None:
        return True
    return datetime.now() - last_time >= timedelta(hours=2)

def run_data_fetcher():
    if not can_run("data_fetcher"):
        print(f"[{datetime.now()}] Skipping data_fetcher: ran too recently.")
        return
    print(f"[{datetime.now()}] Running data_fetcher...")
    subprocess.run(["python", r"S:\ecom-central\ecom-central\data_fetcher.py"], shell=True)
    last_run["data_fetcher"] = datetime.now()

def run_cron_job():
    if not can_run("cron_job"):
        print(f"[{datetime.now()}] Skipping cron_job: ran too recently.")
        return
    print(f"[{datetime.now()}] Running cron_job...")
    subprocess.run(["python", r"S:\ecom-central\ecom-central\cron_job.py"], shell=True)
    last_run["cron_job"] = datetime.now()

# Schedule jobs
schedule.every(6).hours.do(run_data_fetcher)
schedule.every().day.at("08:07").do(run_cron_job)
schedule.every().day.at("20:07").do(run_cron_job)

print("=== Local Scheduler Started ===")
while True:
    schedule.run_pending()
    time.sleep(30)
