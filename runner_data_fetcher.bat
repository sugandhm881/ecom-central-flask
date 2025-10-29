@echo off
:: Sets the character set to prevent encoding errors
chcp 65001 > nul
:: Runs the data_fetcher.py script using the python from the virtual environment
"S:\ecom-central\ecom-central\venv\Scripts\python.exe" "S:\ecom-central\ecom-central\data_fetcher.py"