@echo off
:: Sets the character set to prevent encoding errors
chcp 65001 > nul
:: Runs the cron_job.py script using the python from the virtual environment
"S:\ecom-central\ecom-central\venv\Scripts\python.exe" "S:\ecom-central\ecom-central\cron_job.py"