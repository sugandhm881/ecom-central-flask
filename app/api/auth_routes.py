from flask import Blueprint, request, jsonify, current_app
from ..auth import generate_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Handles the login request from the frontend."""
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password are required!'}), 400

    # Get the credentials provided by the user in the form
    email_attempt = data.get('email')
    password_attempt = data.get('password')

    # Get the valid credentials securely from the .env file via the config
    valid_email = current_app.config.get('APP_USER_EMAIL')
    valid_password = current_app.config.get('APP_USER_PASSWORD')

    # --- THIS IS THE NEW SECURITY CHECK ---
    # First, check if the server admin has set the credentials in the .env file.
    # If not, deny all login attempts and log an error.
    if not valid_email or not valid_password:
        print("--- [SECURITY WARNING] Login attempt failed: APP_USER_EMAIL or APP_USER_PASSWORD is not set in the .env file. ---")
        return jsonify({'message': 'Server configuration error. Cannot process login.'}), 500
    # --- END OF SECURITY CHECK ---

    # Now, compare the user's attempt with the valid credentials
    if email_attempt == valid_email and password_attempt == valid_password:
        token = generate_token(email_attempt)
        return jsonify({'token': token})

    return jsonify({'message': 'Invalid credentials!'}), 401


@auth_bp.route('/get-login-details', methods=['GET'])
def get_login_details():
    """Provides login details for pre-filling the form in debug mode."""
    if current_app.debug:
        email = current_app.config.get('APP_USER_EMAIL', '')
        password = current_app.config.get('APP_USER_PASSWORD', '')
        return jsonify({'email': email, 'password': password})
    else:
        return jsonify({'error': 'This endpoint is not available in production.'}), 404