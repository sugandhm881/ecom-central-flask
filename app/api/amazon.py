from flask import Blueprint, jsonify, current_app, request, send_file
from .helpers import make_signed_api_request
from ..auth import token_required
from datetime import datetime, timedelta
import json
import os
import time
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


# ---------------- ADD HERE ----------------
def get_fetch_period():
    """Return full period once per day, else month-to-date."""
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    cache_date_file = 'amazon_cache_date.txt'

    full_fetch = False
    if not os.path.exists(cache_date_file):
        full_fetch = True
    else:
        with open(cache_date_file, 'r') as f:
            last_fetch_date = f.read().strip()
        if last_fetch_date != today_str:
            full_fetch = True

    # Save today as last fetch date
    with open(cache_date_file, 'w') as f:
        f.write(today_str)

    if full_fetch:
        ninety_days_ago = get_fetch_period()
    else:
        month_start = datetime.utcnow().replace(day=1)
        ninety_days_ago = month_start.isoformat() + 'Z'

    return ninety_days_ago
# ---------------- END ADD ----------------

amazon_bp = Blueprint('amazon', __name__)
AMAZON_CACHE_FILE = 'amazon_cache.json'
AMAZON_ITEMS_CACHE_FILE = 'amazon_items_cache.json'
CACHE_DURATION_SECONDS = 30 * 60  # Cache for 10 minutes

def fetch_amazon_orders(config):
    """
    Fetches Amazon orders, using a file-based cache to avoid rate-limiting.
    NOW includes a request for PII data elements.
    """
    if os.path.exists(AMAZON_CACHE_FILE):
        cache_age = time.time() - os.path.getmtime(AMAZON_CACHE_FILE)
        if cache_age < CACHE_DURATION_SECONDS:
            print("\n--- [Amazon Cache] Using cached data. Age: {:.0f} seconds. ---".format(cache_age))
            with open(AMAZON_CACHE_FILE, 'r') as f:
                return json.load(f)

    print("\n--- [Amazon Cache] Cache is old or missing. Fetching fresh data from API. ---")
    required_keys = ['AWS_ACCESS_KEY', 'AWS_SECRET_KEY', 'AWS_REGION', 'LWA_CLIENT_ID', 'LWA_CLIENT_SECRET', 'REFRESH_TOKEN', 'MARKETPLACE_ID']
    if not all(config.get(key) for key in required_keys):
        print("[WARNING] Amazon SP-API credentials not set. Skipping Amazon orders.")
        return []

    ninety_days_ago = (datetime.utcnow() - timedelta(days=180)).isoformat() + 'Z'
    all_amazon_orders_raw, next_token = [], None
    page = 1
    consecutive_quota_errors = 0
    
    try:
        while True:
            print(f"[Amazon API] Fetching page {page}...")
            query_params = {
                'MarketplaceIds': config['MARKETPLACE_ID'], 
                'CreatedAfter': ninety_days_ago,
                # --- THIS IS THE FIX FOR PII ---
                # Request buyer info and shipping address, which are restricted data elements.
                'dataElements': 'buyerInfo,shippingAddress'
            }
            if next_token: 
                query_params['NextToken'] = next_token
            
            options = {
                'method': 'GET', 
                'path': '/orders/v0/orders', 
                'queryParams': query_params
            }
            
            try:
                response_data = make_signed_api_request(config, options)
                
                payload = response_data.get('payload', {})
                orders_payload = payload.get('Orders', [])
                all_amazon_orders_raw.extend(orders_payload)
                
                print(f"[Amazon API] Fetched page {page} ({len(orders_payload)} orders, total: {len(all_amazon_orders_raw)})")
                
                consecutive_quota_errors = 0
                next_token = payload.get('NextToken')
                page += 1
                
                if not next_token: 
                    break
                
                if page <= 5: time.sleep(2)
                elif page <= 10: time.sleep(3)
                else: time.sleep(5)
                    
            except Exception as api_error:
                error_str = str(api_error)
                if 'QuotaExceeded' in error_str or 'quota' in error_str.lower():
                    consecutive_quota_errors += 1
                    wait_time = 60 * consecutive_quota_errors
                    print(f"[Amazon API] Quota exceeded at page {page}, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    
                    if consecutive_quota_errors >= 5:
                        print(f"[Amazon API] Too many quota errors, stopping at {len(all_amazon_orders_raw)} orders")
                        break
                    continue
                else:
                    raise api_error

        print(f"✅ Successfully fetched a total of {len(all_amazon_orders_raw)} Amazon orders.")
        
        with open(AMAZON_CACHE_FILE + '.raw', 'w') as f:
            json.dump(all_amazon_orders_raw, f)
        
        normalized_orders = [normalize_amazon_order(order) for order in all_amazon_orders_raw]
        
        with open(AMAZON_CACHE_FILE, 'w') as f:
            json.dump(normalized_orders, f)
            
        return normalized_orders

    except Exception as e:
        print(f"--- [ERROR] The Amazon SP-API request failed. Error: {e} ---")
        return []

def normalize_amazon_order(order):
    """Normalize Amazon order, now correctly extracting PII data."""
    address = order.get('ShippingAddress', {}) or {}
    buyer_info = order.get('BuyerInfo', {}) or {}
    
    # --- FIX: Extract buyer name from PII data ---
    customer_name = buyer_info.get('BuyerName', 'N/A')
    if customer_name == 'N/A': # Fallback for some cases
        customer_name = address.get('Name', 'N/A')

    order_date_raw = order.get('PurchaseDate', '')
    try:
        order_date = datetime.fromisoformat(order_date_raw.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except:
        order_date = order_date_raw
    
    return {
        "platform": "Amazon", 
        "id": order['AmazonOrderId'], 
        "originalId": order['AmazonOrderId'],
        "date": order_date,
        "name": customer_name, # <-- Use the extracted name
        "total": float(order.get('OrderTotal', {}).get('Amount', 0)),
        "status": {
            'Pending': 'New', 
            'Unshipped': 'New', 
            'PartiallyShipped': 'Processing', 
            'Shipped': 'Shipped', 
            'Canceled': 'Cancelled'
        }.get(order['OrderStatus'], 'Processing'),
        "items": [], # Items will be fetched in a separate step
        "address": f"{address.get('AddressLine1', '')}, {address.get('City', '')}".strip(', ') or 'No address',
        "paymentMethod": order.get('PaymentMethod', 'N/A')
    }

def get_cached_order_items(order_id):
    """Get items for an order from cache"""
    if os.path.exists(AMAZON_ITEMS_CACHE_FILE):
        try:
            with open(AMAZON_ITEMS_CACHE_FILE, 'r') as f:
                items_cache = json.load(f)
                if order_id in items_cache:
                    return items_cache[order_id]
        except:
            pass
    return None

def save_order_items_to_cache(order_id, items):
    """Save items for an order to cache"""
    items_cache = {}
    if os.path.exists(AMAZON_ITEMS_CACHE_FILE):
        try:
            with open(AMAZON_ITEMS_CACHE_FILE, 'r') as f:
                items_cache = json.load(f)
        except:
            pass
    
    items_cache[order_id] = items
    
    with open(AMAZON_ITEMS_CACHE_FILE, 'w') as f:
        json.dump(items_cache, f)

def fetch_order_items_batch(config, order_ids, auto_fetch=False):
    """Fetch items for multiple orders with quota handling and caching"""
    order_items_map = {}
    
    print(f"[Amazon] Loading items from cache for {len(order_ids)} orders...")
    
    missing_order_ids = []
    for order_id in order_ids:
        cached_items = get_cached_order_items(order_id)
        if cached_items is not None:
            order_items_map[order_id] = cached_items
        else:
            missing_order_ids.append(order_id)
            order_items_map[order_id] = []
    
    cached_count = sum(1 for items in order_items_map.values() if items)
    print(f"[Amazon] Loaded {cached_count}/{len(order_ids)} orders with items from cache")
    
    if auto_fetch and missing_order_ids:
        print(f"[Amazon] Auto-fetching items for {len(missing_order_ids)} orders...")
        print(f"[Amazon] ⚠️ This will take approximately {len(missing_order_ids) * 0.5:.0f} seconds due to API rate limits")
        
        def fetch_single_order_items(order_id):
            """Fetch items for a single order with retry logic"""
            retry_count = 0
            max_retries = 2
            
            while retry_count < max_retries:
                try:
                    options = {
                        'method': 'GET',
                        'path': f'/orders/v0/orders/{order_id}/orderItems',
                        'queryParams': {}
                    }
                    
                    response_data = make_signed_api_request(config, options)
                    items = response_data.get('payload', {}).get('OrderItems', [])
                    save_order_items_to_cache(order_id, items)
                    return (order_id, items, None)
                    
                except Exception as e:
                    error_str = str(e)
                    if 'QuotaExceeded' in error_str or 'quota' in error_str.lower():
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(10)
                    else:
                        save_order_items_to_cache(order_id, [])
                        return (order_id, [], str(e))
            
            save_order_items_to_cache(order_id, [])
            return (order_id, [], "Max retries exceeded")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        fetched_count = 0
        error_count = 0
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_single_order_items, order_id): order_id 
                      for order_id in missing_order_ids}
            
            for future in as_completed(futures):
                order_id, items, error = future.result()
                
                if error:
                    error_count += 1
                    if error_count <= 5:
                        print(f"[Amazon] ❌ Failed to fetch items for {order_id}: {error}")
                else:
                    order_items_map[order_id] = items
                    fetched_count += 1
                
                total_processed = fetched_count + error_count
                if total_processed % 50 == 0:
                    print(f"[Amazon] Progress: {total_processed}/{len(missing_order_ids)} orders processed ({fetched_count} success, {error_count} failed)")
                
                time.sleep(0.5)
        
        print(f"[Amazon] ✅ Auto-fetch complete: {fetched_count} fetched, {error_count} failed")
    
    return order_items_map