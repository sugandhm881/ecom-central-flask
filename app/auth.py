import jwt
from functools import wraps
from flask import request, jsonify, current_app
import datetime

def generate_token(email):
    """Generates a JSON Web Token (JWT) for the authenticated user."""
    try:
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1), # Token expires in 1 day
            'iat': datetime.datetime.utcnow(),
            'sub': email
        }
        # Sign the token with the secret key from your config
        return jwt.encode(
            payload,
            current_app.config.get('SECRET_KEY'),
            algorithm='HS256'
        )
    except Exception as e:
        return str(e)

def token_required(f):
    """
    This is a decorator. You can add @token_required above any route 
    to make it a protected route that requires a valid token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Check if the token is in the 'Authorization' header
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({'message': 'Authentication token is missing!'}), 401

        try:
            # Decode the token to ensure it's valid and not expired
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired! Please log in again.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(*args, **kwargs)
    return decorated