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

from .helpers import get_all_shopify_orders_paginated, get_facebook_ads, get_order_source_term, load_cache, save_cache, get_raw_rapidshyp_status, normalize_status, pick_date_for_filter

adset_performance_bp = Blueprint('adset_performance', __name__)
MASTER_DATA_FILE = 'master_order_data.json'


def load_master_orders_utf8_safe(path):
    """
    Safely load the master orders JSON file with UTF-8 encoding.
    Falls back to error-tolerant mode if the file contains invalid UTF-8 bytes.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError as e:
        # Fallback: tolerate bad bytes to keep the API alive
        print(f"[WARN] UTF-8 decode failed for {path} at position {e.start}: {e.reason}")
        print("[WARN] Retrying with errors='replace'. Consider regenerating the file by running data_fetcher.py")
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return json.load(f)


def create_empty_bucket(bucket_id, name, spend=0):
    return {
        'id': bucket_id,
        'name': name,
        'spend': spend,
        'totalOrders': 0,
        'revenue': 0,
        'deliveredOrders': 0,
        'deliveredRevenue': 0,  # Added deliveredRevenue initialization
        'rtoOrders': 0,
        'cancelledOrders': 0,
        'inTransitOrders': 0,
        'processingOrders': 0,
        'exceptionOrders': 0,
        'terms': {}
    }


def process_order_into_bucket(order, bucket, status, adset_id=None, adset_revenue_acc=None):
    bucket['totalOrders'] += 1
    order_revenue = float(order.get('total_price', 0))
    if status not in ['Cancelled', 'RTO']:
        bucket['revenue'] += order_revenue
    if status == 'Delivered':
        bucket['deliveredOrders'] += 1
        bucket['deliveredRevenue'] = bucket.get('deliveredRevenue', 0) + order_revenue
        if adset_id and adset_revenue_acc is not None:
            adset_revenue_acc[adset_id] = adset_revenue_acc.get(adset_id, 0) + order_revenue
    elif status == 'RTO':
        bucket['rtoOrders'] += 1
    elif status == 'Cancelled':
        bucket['cancelledOrders'] += 1
    elif status == 'In-Transit':
        bucket['inTransitOrders'] += 1
    elif status == 'Processing':
        bucket['processingOrders'] += 1
    elif status == 'Exception':
        bucket['exceptionOrders'] += 1


def get_adset_performance_data(since, until, config, date_filter_type):
    """
    Core logic to compute adset performance data.
    Now requires 'date_filter_type' to be passed in.
    """
    start_date = datetime.strptime(since, '%Y-%m-%d').date()
    end_date = datetime.strptime(until, '%Y-%m-%d').date()

    if not os.path.exists(MASTER_DATA_FILE):
        raise FileNotFoundError("Master data file not found. Please run data_fetcher.py first.")
    
    all_orders = load_master_orders_utf8_safe(MASTER_DATA_FILE)
    
    shopify_orders_in_range = []
    for o in all_orders:
        filter_date = pick_date_for_filter(o, date_filter_type)
        if filter_date and start_date <= filter_date <= end_date:
            shopify_orders_in_range.append(o)

    fb_ads = get_facebook_ads(config, since, until)

    performance_data, fb_ad_map = {}, {ad['ad_id']: ad for ad in fb_ads}
    for ad in fb_ads:
        if ad['adset_id'] not in performance_data:
            performance_data[ad['adset_id']] = create_empty_bucket(ad['adset_id'], ad['adset_name'])
        performance_data[ad['adset_id']]['terms'][ad['ad_id']] = create_empty_bucket(ad['ad_id'], ad['ad_name'], spend=ad['spend'])
    
    UNATTRIBUTED_ID = 'unattributed'
    performance_data[UNATTRIBUTED_ID] = create_empty_bucket(UNATTRIBUTED_ID, "Unattributed Sales")

    adset_delivered_revenue_totals = {}

    for order in shopify_orders_in_range:
        source, term = get_order_source_term(order)
        raw_status = order.get('raw_rapidshyp_status')
        status = normalize_status(order, raw_status)
        
        adset_bucket, term_bucket = None, None
        adset_id_for_revenue = None
        if source == 'facebook_ad':
            matched_ad = fb_ad_map.get(term)
            if matched_ad:
                adset_bucket = performance_data.get(matched_ad['adset_id'])
                adset_id_for_revenue = matched_ad['adset_id']
                if adset_bucket:
                    term_bucket = adset_bucket['terms'].get(matched_ad['ad_id'])
        if not term_bucket:
            adset_bucket = performance_data[UNATTRIBUTED_ID]
            adset_id_for_revenue = UNATTRIBUTED_ID
            if source not in adset_bucket['terms']:
                adset_bucket['terms'][source] = create_empty_bucket(source, term)
            term_bucket = adset_bucket['terms'][source]
        
        process_order_into_bucket(order, adset_bucket, status, adset_id_for_revenue, adset_delivered_revenue_totals)
        if term_bucket is not adset_bucket:
            process_order_into_bucket(order, term_bucket, status)

    result = []
    for adset_id, adset in performance_data.items():
        adset['spend'] = sum(term.get('spend', 0) for term in adset.get('terms', {}).values())
        adset['deliveredRevenue'] = sum(term.get('deliveredRevenue', 0) for term in adset.get('terms', {}).values())  # Aggregate deliveredRevenue from terms
        if adset.get('totalOrders', 0) > 0 or adset['spend'] > 0:
            adset['terms'] = sorted(
                [t for t in adset['terms'].values() if t['totalOrders'] > 0 or t['spend'] > 0],
                key=lambda x: x.get('totalOrders', 0),
                reverse=True
            )
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
        date_filter_type = request.args.get('date_filter_type', 'created_at')  # Get the filter type
        if not since or not until:
            return jsonify({"error": "A 'since' and 'until' date range is required."}), 400
            
        data = get_adset_performance_data(since, until, current_app.config, date_filter_type)
        return jsonify(data)
    except Exception as e:
        print(f"--- [CRITICAL Adset Performance ERROR] ---")
        traceback.print_exc()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500