from flask import Blueprint, jsonify, request, current_app
import requests
import json
import os
from datetime import datetime, timedelta
from ..auth import token_required
import time
import traceback
from urllib.parse import urlparse
import pytz

# It's better to import these from a central place if they are used elsewhere,
# but for this file's purpose, let's ensure they are defined.
from .helpers import get_all_shopify_orders_paginated, get_facebook_ads, get_order_source_term, load_cache, save_cache, get_raw_rapidshyp_status, normalize_status

adset_performance_bp = Blueprint('adset_performance', __name__)
MASTER_DATA_FILE = 'master_order_data.json'

def create_empty_bucket(bucket_id, name, spend=0):
    return {'id': bucket_id, 'name': name, 'spend': spend, 'totalOrders': 0, 'revenue': 0, 'deliveredOrders': 0, 'rtoOrders': 0, 'cancelledOrders': 0, 'inTransitOrders': 0, 'processingOrders': 0, 'exceptionOrders': 0, 'terms': {}}

def process_order_into_bucket(order, bucket, status):
    bucket['totalOrders'] += 1
    if status not in ['Cancelled', 'RTO']: bucket['revenue'] += float(order.get('total_price', 0))
    if status == 'Delivered': bucket['deliveredOrders'] += 1
    elif status == 'RTO': bucket['rtoOrders'] += 1
    elif status == 'Cancelled': bucket['cancelledOrders'] += 1
    elif status == 'In-Transit': bucket['inTransitOrders'] += 1
    elif status == 'Processing': bucket['processingOrders'] += 1
    elif status == 'Exception': bucket['exceptionOrders'] += 1

# --- DEFINITIVE VERSION of the data function ---
def get_adset_performance_data(since, until, config):
    """
    Core logic to compute adset performance data.
    Now requires 'since', 'until', and 'config' to be passed in.
    """
    start_date = datetime.strptime(since, '%Y-%m-%d').date()
    end_date = datetime.strptime(until, '%Y-%m-%d').date()
    print(f"\n--- [Adset Performance Data] Processing for: {since} to {until} ---")

    if not os.path.exists(MASTER_DATA_FILE):
        raise FileNotFoundError("Master data file not found. Please run data_fetcher.py first.")
    
    with open(MASTER_DATA_FILE, 'r', encoding='utf-8') as f:  
        all_orders = json.load(f)
    
    shopify_orders_in_range = [o for o in all_orders if start_date <= datetime.fromisoformat(o['created_at']).date() <= end_date]
    print(f"Filtered to {len(shopify_orders_in_range)} orders created in range.")

    fb_ads = get_facebook_ads(config, since, until)

    performance_data, fb_ad_map = {}, {ad['ad_id']: ad for ad in fb_ads}
    for ad in fb_ads:
        if ad['adset_id'] not in performance_data: performance_data[ad['adset_id']] = create_empty_bucket(ad['adset_id'], ad['adset_name'])
        performance_data[ad['adset_id']]['terms'][ad['ad_id']] = create_empty_bucket(ad['ad_id'], ad['ad_name'], spend=ad['spend'])
    
    UNATTRIBUTED_ID = 'unattributed'
    performance_data[UNATTRIBUTED_ID] = create_empty_bucket(UNATTRIBUTED_ID, "Unattributed Sales")

    for order in shopify_orders_in_range:
        source, term = get_order_source_term(order)
        raw_status = order.get('raw_rapidshyp_status')
        status = normalize_status(order, raw_status)
        
        adset_bucket, term_bucket = None, None
        if source == 'facebook_ad':
            matched_ad = fb_ad_map.get(term)
            if matched_ad:
                adset_bucket = performance_data.get(matched_ad['adset_id'])
                if adset_bucket: term_bucket = adset_bucket['terms'].get(matched_ad['ad_id'])
        if not term_bucket:
            adset_bucket = performance_data[UNATTRIBUTED_ID]
            if source not in adset_bucket['terms']: adset_bucket['terms'][source] = create_empty_bucket(source, term)
            term_bucket = adset_bucket['terms'][source]
        
        process_order_into_bucket(order, adset_bucket, status)
        if term_bucket is not adset_bucket:
            process_order_into_bucket(order, term_bucket, status)

    result = []
    for adset_id, adset in performance_data.items():
        adset['spend'] = sum(term.get('spend', 0) for term in adset.get('terms', {}).values())
        if adset.get('totalOrders', 0) > 0 or adset['spend'] > 0:
            adset['terms'] = sorted([t for t in adset['terms'].values() if t['totalOrders'] > 0 or t['spend'] > 0], key=lambda x: x.get('totalOrders', 0), reverse=True)
            result.append(adset)
    
    return {'adsetPerformance': sorted(result, key=lambda x: x.get('spend', 0), reverse=True)}


@adset_performance_bp.route('/get-adset-performance', methods=['GET'])
@token_required
def get_adset_performance_route():
    """
    Flask API route. It gets data from the request and passes it to the core logic function.
    """
    try:
        since = request.args.get('since')
        until = request.args.get('until')
        if not since or not until:
            return jsonify({"error": "A 'since' and 'until' date range is required."}), 400
            
        # Call the reusable function with the required arguments
        data = get_adset_performance_data(since, until, current_app.config)
        return jsonify(data)
    except Exception as e:
        print(f"--- [CRITICAL Adset Performance ERROR] ---"); traceback.print_exc()
        return jsonify({"error": f"An internal server error occurred: {e}"}), 500