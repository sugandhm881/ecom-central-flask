import hashlib
import hmac
from datetime import datetime, timezone
import requests
import time
import random
from urllib.parse import urlencode

# --- Global cache for LWA token ---
lwa_token_cache = {
    "token": None,
    "expires_at": 0
}

def get_lwa_access_token(config):
    """
    Fetches a Login with Amazon (LWA) access token, using a simple in-memory cache.
    """
    now = time.time()
    if lwa_token_cache["token"] and lwa_token_cache["expires_at"] > now:
        return lwa_token_cache["token"]

    try:
        response = requests.post('https://api.amazon.com/auth/o2/token', json={
            'grant_type': 'refresh_token',
            'refresh_token': config['REFRESH_TOKEN'],
            'client_id': config['LWA_CLIENT_ID'],
            'client_secret': config['LWA_CLIENT_SECRET']
        })
        response.raise_for_status()
        data = response.json()
        
        lwa_token_cache["token"] = data['access_token']
        # Set expiry to 5 minutes before the actual token expiry for a safety margin
        lwa_token_cache["expires_at"] = now + data.get('expires_in', 3600) - 300
        
        return lwa_token_cache["token"]
    except requests.exceptions.RequestException as e:
        print(f"LWA token error: {e.response.text if e.response else e}")
        raise Exception("Failed to retrieve LWA access token from Amazon.")


def sign(key, msg):
    """Helper function for HMAC-SHA256 signing."""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def get_signature_key(key, date_stamp, region_name, service_name):
    """Derives the AWS Signature Version 4 signing key."""
    k_date = sign(('AWS4' + key).encode('utf-8'), date_stamp)
    k_region = sign(k_date, region_name.encode('utf-8'))
    k_service = sign(k_region, service_name.encode('utf-8'))
    k_signing = sign(k_service, b'aws4_request')
    return k_signing

def make_signed_api_request(config, options, max_retries=5):
    """
    Constructs and sends a signed AWS Signature V4 request to the Amazon SP-API.
    Includes exponential backoff for rate limiting (429 errors).
    """
    access_token = get_lwa_access_token(config)
    host = config['BASE_URL'].replace('https://', '')
    service = 'execute-api' # This is the service name for SP-API
    method = options['method']
    path = options['path']
    query_params = options.get('queryParams', {})

    t = datetime.now(timezone.utc)
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')

    canonical_uri = path
    # Sort query parameters for the canonical request
    canonical_querystring = urlencode(sorted(query_params.items()))
    
    canonical_headers = f"host:{host}\nx-amz-access-token:{access_token}\nx-amz-date:{amz_date}\n"
    signed_headers = 'host;x-amz-access-token;x-amz-date'
    
    # The payload is an empty string for GET requests
    payload_hash = hashlib.sha256(b'').hexdigest()

    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{date_stamp}/{config['AWS_REGION']}/{service}/aws4_request"
    string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

    signing_key = get_signature_key(config['AWS_SECRET_KEY'], date_stamp, config['AWS_REGION'], service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    authorization_header = f"{algorithm} Credential={config['AWS_ACCESS_KEY']}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

    headers = {
        'x-amz-access-token': access_token,
        'x-amz-date': amz_date,
        'Authorization': authorization_header,
    }

    url = f"{config['BASE_URL']}{path}"

    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, params=query_params)
            
            if response.status_code == 429: # Rate limited
                delay = (2 ** attempt) + (random.random())
                print(f"Rate limited by SP-API. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
                continue # Retry the loop
            
            response.raise_for_status() # Raise HTTPError for other bad responses (4xx or 5xx)
            
            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            print(f"Amazon SP-API request failed: {e}")
            if attempt >= max_retries - 1:
                raise Exception(f"Max retries exceeded for SP-API request. Last error: {e}")

    raise Exception("Max retries exceeded for SP-API request.")