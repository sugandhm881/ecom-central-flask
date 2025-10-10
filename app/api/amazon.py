from flask import Blueprint, jsonify, current_app, request # <-- ADD 'request' HERE
from .helpers import make_signed_api_request
from ..auth import token_required
from datetime import datetime, timedelta
import json
import os
import time

amazon_bp = Blueprint('amazon', __name__)
AMAZON_CACHE_FILE = 'amazon_cache.json'
CACHE_DURATION_SECONDS = 10 * 60 # Cache for 10 minutes

def fetch_amazon_orders(config):
    """
    Fetches Amazon orders, using a file-based cache to avoid rate-limiting.
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

    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    all_amazon_orders_raw, next_token = [], None
    page = 1
    
    try:
        while True:
            print(f"[Amazon API] Fetching page {page}...")
            query_params = {'MarketplaceIds': config['MARKETPLACE_ID'], 'CreatedAfter': thirty_days_ago}
            if next_token: query_params['NextToken'] = next_token
            options = {'method': 'GET', 'path': '/orders/v0/orders', 'queryParams': query_params}
            
            response_data = make_signed_api_request(config, options)
            
            payload = response_data.get('payload', {})
            orders_payload = payload.get('Orders', [])
            all_amazon_orders_raw.extend(orders_payload)
            
            next_token = payload.get('NextToken')
            page += 1
            if not next_token: break

        print(f"✅ Successfully fetched a total of {len(all_amazon_orders_raw)} Amazon orders.")
        
        normalized_orders = [normalize_amazon_order(order) for order in all_amazon_orders_raw]
        with open(AMAZON_CACHE_FILE, 'w') as f:
            json.dump(normalized_orders, f)
            
        return normalized_orders

    except Exception as e:
        print(f"--- [ERROR] The Amazon SP-API request failed. Error: {e} ---")
        return []

def normalize_amazon_order(order):
    address = order.get('ShippingAddress', {}) or {}
    return {
        "platform": "Amazon", "id": order['AmazonOrderId'], "originalId": order['AmazonOrderId'],
        "date": datetime.fromisoformat(order['PurchaseDate']).strftime('%Y-%m-%d'), "name": 'N/A',
        "total": float(order.get('OrderTotal', {}).get('Amount', 0)),
        "status": {'Pending': 'New', 'Unshipped': 'New', 'PartiallyShipped': 'Processing', 'Shipped': 'Shipped', 'Canceled': 'Cancelled'}.get(order['OrderStatus'], 'Processing'),
        "items": [], "address": f"{address.get('AddressLine1', '')}, {address.get('City', '')}".strip(', ') or 'No address',
        "paymentMethod": order.get('PaymentMethod', 'N/A')
    }

@amazon_bp.route('/get-amazon-buyer-info', methods=['GET'])
@token_required
def get_amazon_buyer_info():
    order_id = request.args.get('orderId')
    if not order_id: return jsonify({"error": "orderId parameter is required"}), 400
    try:
        options = {'method': 'GET', 'path': f'/orders/v0/orders/{order_id}/buyerInfo', 'queryParams': {}}
        data = make_signed_api_request(current_app.config, options)
        return jsonify({"name": data.get('payload', {}).get('BuyerName', 'N/A')})
    except Exception as e:
        return jsonify({"error": str(e)}), 500