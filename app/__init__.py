from flask import Flask
from .config import Config

def create_app():
    """
    This is the application factory. It creates and configures the Flask app.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    with app.app_context():
        # Import all the different parts (blueprints) of your application
        from . import routes
        from .api import auth_routes
        from .api import orders
        from .api import ad_performance
        from .api import adset_performance
        from .api import amazon
        from .api import pdf_generator
        from .api import shipping
        from .api import excel_report
        from .api import webhook_handler # <-- ADD THIS IMPORT

        # Register each blueprint with the main app
        app.register_blueprint(routes.main_bp)
        app.register_blueprint(auth_routes.auth_bp, url_prefix='/api')
        app.register_blueprint(orders.orders_bp, url_prefix='/api')
        app.register_blueprint(ad_performance.ad_performance_bp, url_prefix='/api')
        app.register_blueprint(adset_performance.adset_performance_bp, url_prefix='/api')
        app.register_blueprint(amazon.amazon_bp, url_prefix='/api')
        app.register_blueprint(pdf_generator.pdf_bp, url_prefix='/api')
        app.register_blueprint(shipping.shipping_bp, url_prefix='/api')
        app.register_blueprint(excel_report.excel_report_bp, url_prefix='/api')
        app.register_blueprint(webhook_handler.webhook_bp, url_prefix='/api/webhook') # <-- ADD THIS REGISTRATION

    return app