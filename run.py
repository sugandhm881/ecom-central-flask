from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

# Create Flask app instance
app = create_app()

# ✅ Fix for HTTPS behind Nginx reverse proxy
# This ensures Flask correctly recognizes secure requests
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

if __name__ == '__main__':
    # Run only for local testing — not used in production with Gunicorn
    app.run(debug=True)
