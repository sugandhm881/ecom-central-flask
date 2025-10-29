import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
import pytz

# Ensure the app path is added if running cron_job.py from the root directory
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import create_app
from app.api.adset_performance import get_adset_performance_data
from app.api.pdf_generator import PDF

def send_email_with_attachment(pdf_data, since, until):
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_host = os.environ.get('EMAIL_HOST')
    email_port = int(os.environ.get('EMAIL_PORT', 587))
    recipient_email = os.environ.get('RECIPIENT_EMAIL')
    if not all([email_user, email_password, email_host, recipient_email]):
        print("[EMAIL ERROR] Email configuration is missing from the .env file.")
        return

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = recipient_email
    msg['Subject'] = f"Ad Set Performance Report: {since} to {until}"
    msg.attach(MIMEText(f"Attached is the ad set performance report for the period {since} to {until}.", 'plain'))
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_data)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="adset_report_{since}_to_{until}.pdf"')
    msg.attach(part)
    try:
        print(f"Connecting to email server at {email_host}...")
        server = smtplib.SMTP(email_host, email_port)
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, recipient_email, msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {recipient_email}!")
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {e}")

def generate_report():
    app = create_app()
    with app.app_context():
        TZ_INDIA = pytz.timezone('Asia/Kolkata')
        today_in_india = datetime.now(TZ_INDIA)
        since_date = today_in_india.replace(day=1).strftime('%Y-%m-%d')
        until_date = today_in_india.strftime('%Y-%m-%d')
        print(f"Generating report for India date range: {since_date} to {until_date}")

        # --- THIS IS THE FIX ---
        # Added the missing 'date_filter_type' argument
        adset_data = get_adset_performance_data(
            since_date,
            until_date,
            app.config,
            date_filter_type='created_at' # Use Shopify Order Date as default for cron
        )
        # --- END OF FIX ---

        if not adset_data or not adset_data.get('adsetPerformance'):
            print("No performance data found for the period. Aborting report."); return

        print("Generating PDF...")
        pdf = PDF()
        pdf.add_page(); pdf.create_summary(adset_data['adsetPerformance'], since_date, until_date); pdf.create_table(adset_data['adsetPerformance'])
        
        pdf_output_bytes = pdf.output()
        
        print(f"PDF generated successfully ({len(pdf_output_bytes)} bytes).")
        if len(pdf_output_bytes) > 0:
            send_email_with_attachment(pdf_output_bytes, since_date, until_date)
        else:
            print("[ERROR] PDF generation resulted in a 0-byte file. Email will not be sent.")

if __name__ == '__main__':
    generate_report()