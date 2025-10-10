@echo off
echo Activating virtual environment and running script...
call venv\Scripts\activate
python cron_job.py
echo Script finished.
pause