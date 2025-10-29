from app import create_app
import os

# Load environment variables if using python-dotenv locally (optional but good practice)
# from dotenv import load_dotenv
# load_dotenv()

application = create_app()

if __name__ == "__main__":
    # You can specify host and port here for local testing if needed
    # but Gunicorn will handle this on the server.
    application.run()