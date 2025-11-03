import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime, timedelta
import pytz
import calendar

# Ensure the app path is added if running cron_job.py from the root directory
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import create_app
from app.api.adset_performance import get_adset_performance_data
from app.api.pdf_generator import PDF


def send_email_with_attachment(pdf_attachments, since, until):
    """
    pdf_attachments: list of tuples (filename, pdf_bytes)
    """
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
    msg.attach(MIMEText(
        f"Attached are the ad set performance reports:\n\n"
        f"1️⃣ Month-to-Date ({since} → {until})\n"
        f"2️⃣ Last Month\n\n"
        f"Regards,\nEcom Central", 'plain'))

    for filename, pdf_data in pdf_attachments:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
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


def generate_pdf(app, since_date, until_date, label):
    with app.app_context():
        adset_data = get_adset_performance_data(
            since_date,
            until_date,
            app.config,
            date_filter_type='created_at'  # Use Shopify Order Date as default for cron
        )
        if not adset_data or not adset_data.get('adsetPerformance'):
            print(f"No performance data for {label} ({since_date} to {until_date}). Skipping PDF.")
            return None

        print(f"Generating {label} PDF...")
        pdf = PDF()
        pdf.add_page()
        pdf.create_summary(adset_data['adsetPerformance'], since_date, until_date)
        pdf.create_table(adset_data['adsetPerformance'])

        pdf_output_bytes = bytes(pdf.output(dest='S'))
        print(f"{label} PDF generated successfully ({len(pdf_output_bytes)} bytes).")
        return pdf_output_bytes


def generate_report():
    app = create_app()
    TZ_INDIA = pytz.timezone('Asia/Kolkata')
    today_in_india = datetime.now(TZ_INDIA)

    # Month-to-Date
    since_mtd = today_in_india.replace(day=1).strftime('%Y-%m-%d')
    until_mtd = today_in_india.strftime('%Y-%m-%d')

    # Last Month
    first_day_last_month = (today_in_india.replace(day=1) - timedelta(days=1)).replace(day=1)
    last_day_last_month = datetime(first_day_last_month.year, first_day_last_month.month,
                                   calendar.monthrange(first_day_last_month.year, first_day_last_month.month)[1])
    since_last_month = first_day_last_month.strftime('%Y-%m-%d')
    until_last_month = last_day_last_month.strftime('%Y-%m-%d')

    print(f"Generating reports for:")
    print(f"  • Month-to-Date: {since_mtd} → {until_mtd}")
    print(f"  • Last Month: {since_last_month} → {until_last_month}")

    attachments = []

    mtd_pdf = generate_pdf(app, since_mtd, until_mtd, "Month-to-Date")
    if mtd_pdf:
        attachments.append((f"adset_report_{since_mtd}_to_{until_mtd}.pdf", mtd_pdf))

    last_month_pdf = generate_pdf(app, since_last_month, until_last_month, "Last Month")
    if last_month_pdf:
        attachments.append((f"adset_report_{since_last_month}_to_{until_last_month}.pdf", last_month_pdf))

    if attachments:
        send_email_with_attachment(attachments, since_mtd, until_mtd)
    else:
        print("[ERROR] No PDFs generated. No email sent.")


if __name__ == '__main__':
    generate_report()
