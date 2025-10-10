from flask import Blueprint, render_template

# A Blueprint is a way to organize a group of related views and other code.
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Serves the main dashboard page (index.html)."""
    return render_template('index.html')

@main_bp.route('/test-amazon')
def test_amazon():
    """Serves the Amazon API test page (test_amazon.html)."""
    return render_template('test_amazon.html')