from app import create_app

# This creates the Flask application instance using the factory function
# defined in our app/__init__.py file.
app = create_app()

if __name__ == '__main__':
    # This block runs only when you execute "python run.py" directly.
    # The debug=True flag enables auto-reloading when you save a file
    # and provides helpful error pages during development.
    # For a production deployment, this should be set to False.
    app.run(debug=True)