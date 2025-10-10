import hashlib
import hmac
from datetime import datetime, timezone
import requests
import time
import random
from urllib.parse import urlencode, urlparse
import traceback
import json
import os
import pytz

# --- Global cache for LWA token ---
lwa_token_cache = { "token": None, "expires_at": 0 }

# Timezone
TZ_INDIA = pytz.timezone('Asia/Kolkata')

# --- AMAZON SP-API FUNCTIONS ---
def get_lwa_access_token(config):
    now = time.time()
    if lwa_token_cache["token"] and lwa_token_cache["expires_at"] > now: return lwa_token_cache["token"]
    try:
        response = requests.post('https://api.amazon.com/auth/o2/token', json={ 'grant_type': 'refresh_token', 'refresh_token': config['REFRESH_TOKEN'], 'client_id': config['LWA_CLIENT_ID'], 'client_secret': config['LWA_CLIENT_SECRET'] })
        response.raise_for_status()
        data = response.json()
        lwa_token_cache["token"] = data['access_token']
        lwa_token_cache["expires_at"] = now + data.get('expires_in', 3600) - 300
        return lwa_token_cache["token"]
    except requests.exceptions.RequestException as e:
        print(f"LWA token error: {e.response.text if e.response else e}")
        raise Exception("Failed to retrieve LWA access token from Amazon.")

def make_signed_api_request(config, options, max_retries=5):
    print("\n--- [START] Creating New Amazon Signed Request ---")
    try:
        access_token = get_lwa_access_token(config)
        host, service, method, path, query_params = config['BASE_URL'].replace('https://', ''), 'execute-api', options['method'], options['path'], options.get('queryParams', {})
        region, secret_key, access_key = config['AWS_REGION'], config['AWS_SECRET_KEY'], config['AWS_ACCESS_KEY']
        
        t = datetime.now(timezone.utc); amz_date = t.strftime('%Y%m%dT%H%M%SZ'); date_stamp = t.strftime('%Y%m%d')
        canonical_uri, canonical_querystring = path, urlencode(sorted(query_params.items()))
        canonical_headers = f"host:{host}\nx-amz-access-token:{access_token}\nx-amz-date:{amz_date}\n"; signed_headers = 'host;x-amz-access-token;x-amz-date'
        payload_hash = hashlib.sha256(b'').hexdigest()
        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        algorithm = 'AWS4-HMAC-SHA256'; credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        
        def sign_step(key_bytes, msg_string): return hmac.new(key_bytes, msg_string.encode('utf-8'), hashlib.sha256).digest()
        k_secret = ('AWS4' + secret_key).encode('utf-8'); k_date = sign_step(k_secret, date_stamp)
        k_region = sign_step(k_date, region); k_service = sign_step(k_region, service)
        k_signing = sign_step(k_service, 'aws4_request')
        signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        authorization_header = f"{algorithm} Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        headers = {'x-amz-access-token': access_token, 'x-amz-date': amz_date, 'Authorization': authorization_header}
        url = f"{config['BASE_URL']}{path}"
        
        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, headers=headers, params=query_params)
                if response.status_code == 429:
                    delay = (2 ** attempt) + random.random(); time.sleep(delay)
                    continue
                response.raise_for_status()
                print("--- [SUCCESS] Amazon API Request Successful ---\n")
                return response.json() if response.content else {}
            except requests.exceptions.RequestException as e:
                if attempt >= max_retries - 1: raise e
        raise Exception("Max retries exceeded for SP-API request.")
    except Exception as e:
        print(f"--- [CRITICAL ERROR] Amazon request failed: ---"); traceback.print_exc()
        raise e

# --- RAPIDSHYP CACHE ---
CACHE_FILE = 'rapidshyp_cache.json'

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f: json.dump(cache, f, indent=2)

# --- SHOPIFY FUNCTIONS ---
def get_all_shopify_orders_paginated(config, params):
    all_orders, url, page_num = [], f"https://{config['SHOPIFY_SHOP_URL']}/admin/api/2024-07/orders.json", 1
    headers = {'X-Shopify-Access-Token': config['SHOPIFY_TOKEN']}
    while url:
        try:
            response = requests.get(url, headers=headers, params=params); response.raise_for_status()
            data = response.json(); orders_on_page = data.get('orders', [])
            all_orders.extend(orders_on_page)
            print(f"[Shopify] Fetched page {page_num} ({len(orders_on_page)} orders)...")
            link_header, url = response.headers.get('Link'), None
            if link_header:
                links = requests.utils.parse_header_links(link_header)
                for link in links:
                    if link.get('rel') == 'next': url = link.get('url'); params = {}; page_num += 1; break
        except requests.exceptions.RequestException as e:
            print(f"Shopify API Error on page {page_num}: {e}"); break
    print(f"[Shopify] Total orders fetched: {len(all_orders)}")
    return all_orders

# --- RAPIDSHYP FUNCTIONS ---
def get_raw_rapidshyp_status(awb, cache, config):
    """Fetch current RapidShyp status for an AWB."""
    now = time.time()
    if awb in cache:
        entry = cache[awb]
        if isinstance(entry, dict):
            cached_status, last_checked = entry.get('raw_status', entry.get('status')), entry.get('timestamp', 0)
            if any(s in (cached_status or '').upper() for s in ['DELIVERED', 'RTO']) or (now - last_checked) < 3600:
                return cached_status
    url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
    headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
    if not headers["rapidshyp-token"]: return "API Key Missing"
    try:
        res = requests.post(url, headers=headers, json={'awb': awb}, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get('success') and data.get('records'):
            shipment = data['records'][0].get('shipment_details', [{}])[0]
            raw_status = shipment.get('current_tracking_status_desc') or shipment.get('current_tracking_status') or 'Status Not Available'
            cache[awb] = {'raw_status': raw_status, 'timestamp': now}
            return raw_status
    except requests.exceptions.RequestException:
        pass
    return "API Error or Timeout"

def get_rapidshyp_timeline(awb, config):
    """
    Fetch full RapidShyp event timeline for an AWB.
    Returns list of events: [{ "status": "...", "timestamp": "...", "location": "..." }, ...]
    """
    url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
    headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
    if not headers["rapidshyp-token"]: 
        return []
    try:
        res = requests.post(url, headers=headers, json={'awb': awb}, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get('success') and data.get('records'):
            shipment = data['records'][0].get('shipment_details', [{}])[0]
            tracking_history = shipment.get('tracking_history', [])
            events = []
            for event in tracking_history:
                # RapidShyp event structure - adapt field names as needed
                status = event.get('status_desc') or event.get('status') or event.get('current_tracking_status_desc') or ''
                timestamp = event.get('date') or event.get('timestamp') or event.get('event_time') or ''
                location = event.get('location') or event.get('city') or ''
                events.append({
                    'status': status,
                    'timestamp': timestamp,
                    'location': location
                })
            return events
    except requests.exceptions.RequestException as e:
        print(f"RapidShyp timeline fetch error for AWB {awb}: {e}")
    return []

def normalize_status(order, raw_status):
    """Normalize order status based on RapidShyp and Shopify data."""
    if order.get('cancelled_at'): return 'Cancelled'
    if not raw_status or raw_status in ["API Error or Timeout", "Status Not Available", "(blank)"]:
        if order.get('fulfillment_status') == 'fulfilled': return 'Delivered'
        elif order.get('fulfillments'): return 'Processing'
        else: return 'Unfulfilled'
    status_upper = raw_status.upper()
    if "RTO" in status_upper or "RETURN" in status_upper: return 'RTO'
    if "DELIVERED" in status_upper: return 'Delivered'
    if any(s in status_upper for s in ["DELIVERY DELAYED", "IN TRANSIT", "REACHED AT DESTINATION", "UNDELIVERED", "PICKUP COMPLETED", "OUT FOR DELIVERY"]): return 'In-Transit'
    if any(s in status_upper for s in ["LOST", "MISROUTED"]): return 'Exception'
    if any(s in status_upper for s in ["NA", "PICK UP EXCEPTION", "PICKUP CANCELLED"]): return 'Cancelled'
    if any(s in status_upper for s in ["SHIPMENT BOOKED", "OUT FOR PICKUP", "PICKUP SCHEDULED", "CREATED"]): return 'Processing'
    if order.get('fulfillments'): return 'Processing'
    return 'Unfulfilled'

def get_real_order_status(order, rapidshyp_statuses):
    real_status = rapidshyp_statuses.get(order.get('name', ''))
    if real_status: return real_status
    if order.get('cancelled_at'): return 'Cancelled'
    if order.get('fulfillment_status') == 'fulfilled': return 'Delivered'
    return 'Processing'

# --- ATTRIBUTION FUNCTIONS ---
def get_order_source_term(order):
    note_attributes = {attr['name']: attr['value'] for attr in order.get('note_attributes', [])}
    if 'utm_content' in note_attributes and note_attributes['utm_content'].isdigit(): return ('facebook_ad', note_attributes['utm_content'])
    utm_term, utm_source = note_attributes.get('utm_term'), note_attributes.get('utm_source')
    if utm_term: return (utm_source or 'unknown_utm', utm_term)
    if utm_source: return (utm_source, utm_source)
    source_name = order.get('source_name')
    if source_name and source_name not in ['shopify_draft_order', 'pos', 'other']: return (source_name, source_name)
    referring_site = order.get('referring_site')
    if referring_site:
        try:
            domain = urlparse(referring_site).netloc.replace('www.', '')
            if 'google' in domain: return ('google', 'organic')
            if 'facebook' in domain: return ('facebook.com', 'referral')
            if 'instagram' in domain: return ('instagram.com', 'referral')
            return (domain, 'referral')
        except: return ('other_link', 'referral')
    return ('direct', 'direct')

# --- FACEBOOK ADS FUNCTIONS ---
def get_facebook_ads(config, since, until):
    url = f"https://graph.facebook.com/v18.0/act_{config['FACEBOOK_AD_ACCOUNT_ID']}/insights"
    params = {'level': 'ad', 'fields': 'ad_id,ad_name,adset_id,adset_name,spend,campaign_name', 'time_range': f"{{'since':'{since}','until':'{until}'}}", 'limit': 1000, 'access_token': config['FACEBOOK_ACCESS_TOKEN']}
    try:
        r = requests.get(url, params=params); r.raise_for_status(); data = r.json().get('data', [])
        return [{**ad, 'spend': float(ad.get('spend', 0))} for ad in data]
    except Exception as e: print(f"FB Adset API Error: {e}"); return []

# --- DATE FILTER HELPERS WITH TIMEZONE SUPPORT ---
def safe_parse_date(dt_str):
    """
    Parse datetime string to timezone-aware datetime object in IST.
    Returns None on failure.
    """
    if not dt_str:
        return None
    
    try:
        # Handle ISO format with timezone (Shopify format)
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        # Convert to IST
        return dt.astimezone(TZ_INDIA)
    except Exception:
        pass
    
    # Try common formats without timezone (assume IST)
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d-%m-%Y %H:%M:%S', '%d-%m-%Y', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']:
        try:
            dt = datetime.strptime(dt_str, fmt)
            # Localize to IST if naive
            if dt.tzinfo is None:
                dt = TZ_INDIA.localize(dt)
            return dt
        except:
            continue
    
    return None

def infer_shipped_datetime(order):
    """
    Infer first shipped/picked-up time from RapidShyp timeline, fallback to Shopify fulfillments.
    Returns timezone-aware datetime in IST or None.
    """
    # 1) RapidShyp events (if persisted in master_order_data.json)
    events = order.get('rapidshyp_events') or []
    candidates = []
    for ev in events:
        status = (ev.get('status') or ev.get('status_desc') or ev.get('desc') or '').upper()
        t = safe_parse_date(ev.get('timestamp') or ev.get('time') or ev.get('event_time') or ev.get('date'))
        if not t:
            continue
        # Keywords that indicate shipping began
        if any(k in status for k in [
            'PICKUP COMPLETED', 'OUT FOR PICKUP', 'IN TRANSIT', 'SHIPMENT BOOKED',
            'PICKUP SCHEDULED', 'PICKUP CONFIRMED', 'DISPATCHED', 'MANIFESTED',
            'SHIPMENT CREATED', 'PICKED UP', 'MANIFEST', 'OUT FOR DELIVERY'
        ]):
            candidates.append(t)
    if candidates:
        return min(candidates)

    # 2) Shopify fulfillments
    fulfillments = order.get('fulfillments') or []
    candidates = []
    for f in fulfillments:
        t = safe_parse_date(f.get('created_at')) or safe_parse_date(f.get('updated_at'))
        if t:
            candidates.append(t)
    
    if candidates:
        return min(candidates)
    
    return None

def infer_delivered_datetime(order):
    """
    Infer delivered time from RapidShyp timeline, then Shopify fulfillments.
    Returns timezone-aware datetime in IST or None.
    """
    # 1) Explicit field (if you persist it)
    delivered_at = safe_parse_date(order.get('delivered_at'))
    if delivered_at:
        return delivered_at

    # 2) RapidShyp events - look for DELIVERED status
    events = order.get('rapidshyp_events') or []
    delivered_candidates = []
    for ev in events:
        status = (ev.get('status') or ev.get('status_desc') or ev.get('desc') or '').upper()
        t = safe_parse_date(ev.get('timestamp') or ev.get('time') or ev.get('event_time') or ev.get('date'))
        if not t:
            continue
        if 'DELIVERED' in status and 'UNDELIVERED' not in status and 'OUT FOR DELIVERY' not in status:
            delivered_candidates.append(t)
    if delivered_candidates:
        # Use the first delivered timestamp (earliest delivery event)
        return min(delivered_candidates)

    # 3) Shopify fulfillments as proxy (only if marked fulfilled)
    fulfillments = order.get('fulfillments') or []
    if order.get('fulfillment_status') == 'fulfilled' and fulfillments:
        t = safe_parse_date(fulfillments[-1].get('updated_at')) or safe_parse_date(fulfillments[-1].get('created_at'))
        if t:
            return t

    return None

def pick_date_for_filter(order, date_filter_type: str):
    """
    Returns a date (datetime.date in IST) to use for filtering, or None if not applicable.
      - order_date: order['created_at'] converted to IST date
      - shipped_date: inferred from RapidShyp events or Shopify fulfillments
      - delivered_date: inferred from RapidShyp events or Shopify fulfillments (no fallback)
    """
    date_filter_type = (date_filter_type or 'order_date').lower()

    created_dt = safe_parse_date(order.get('created_at'))
    created_date = created_dt.date() if created_dt else None

    if date_filter_type == 'order_date':
        return created_date

    if date_filter_type == 'shipped_date':
        dt = infer_shipped_datetime(order)
        if dt:
            return dt.date()
        # Fallback to created_at for orders without shipment info
        return created_date

    if date_filter_type == 'delivered_date':
        dt = infer_delivered_datetime(order)
        # Only include if we have a real delivered timestamp
        # NO fallback to created_at for delivered filter
        return dt.date() if dt else None

    # Unknown type → default to order_date
    return created_date