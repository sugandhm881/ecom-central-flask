from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config

def create_app():
    """
    This is the application factory. It creates and configures the Flask app.
    """
    app = Flask(
        __name__,
        static_folder="static",        # ensures /static/ is mapped properly
        template_folder="templates"    # ensures templates load correctly
    )
    app.config.from_object(Config)

    # ✅ Fix for HTTPS behind Nginx reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    with app.app_context():
        # Import all the different parts (blueprints) of your application
        from . import routes
        from .api import (
            auth_routes,
            orders,
            ad_performance,
            adset_performance,
            amazon,
            pdf_generator,
            shipping,
            excel_report,
            webhook_handler
        )

        # Register blueprints
        app.register_blueprint(routes.main_bp)
        app.register_blueprint(auth_routes.auth_bp, url_prefix='/api')
        app.register_blueprint(orders.orders_bp, url_prefix='/api')
        app.register_blueprint(ad_performance.ad_performance_bp, url_prefix='/api')
        app.register_blueprint(adset_performance.adset_performance_bp, url_prefix='/api')
        app.register_blueprint(amazon.amazon_bp, url_prefix='/api')
        app.register_blueprint(pdf_generator.pdf_bp, url_prefix='/api')
        app.register_blueprint(shipping.shipping_bp, url_prefix='/api')
        app.register_blueprint(excel_report.excel_report_bp, url_prefix='/api')
        app.register_blueprint(webhook_handler.webhook_bp, url_prefix='/api/webhook')

    return app
