import json
import os
import tempfile
from datetime import datetime, timedelta
import pytz
from app import create_app
from app.api.helpers import (
    get_all_shopify_orders_paginated,
    get_raw_rapidshyp_status,
    get_rapidshyp_timeline,
    save_cache,
    load_cache,
    infer_shipped_datetime,
    infer_delivered_datetime
)
import concurrent.futures

MASTER_DATA_FILE = 'master_order_data.json'
TZ_INDIA = pytz.timezone('Asia/Kolkata')

def atomic_write_json_utf8(path, data):
    """
    Atomically write JSON data to a file with UTF-8 encoding.
    Validates the file after writing to ensure it's readable.
    """
    dir_ = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix='.tmp_', suffix='.json')
    try:
        # Write UTF-8
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Validate read-back as UTF-8
        with open(tmp_path, 'r', encoding='utf-8') as v:
            json.load(v)
        
        # Atomically replace the original file
        os.replace(tmp_path, path)
        print(f"✓ File validated and saved successfully")
    except Exception as e:
        print(f"✗ Error during atomic write: {e}")
        raise
    finally:
        # Clean up temp file if it still exists
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

def enrich_order(order, status_cache, config):
    """
    Enriches a single order with RapidShyp data. This function is designed
    to be run in a separate thread.
    """
    awb = next((f.get('tracking_number') for f in order.get('fulfillments', []) if f.get('tracking_number')), None)
    order['awb'] = awb

    if awb:
        raw_status = get_raw_rapidshyp_status(awb, status_cache, config)
        order['raw_rapidshyp_status'] = raw_status
        timeline = get_rapidshyp_timeline(awb, config)
        order['rapidshyp_events'] = timeline
        shipped_dt = infer_shipped_datetime(order)
        delivered_dt = infer_delivered_datetime(order)
        order['shipped_at'] = shipped_dt.isoformat() if shipped_dt else order.get('shipped_at')
        order['delivered_at'] = delivered_dt.isoformat() if delivered_dt else order.get('delivered_at')
    else:
        order['raw_rapidshyp_status'] = order.get('raw_rapidshyp_status', order.get('fulfillment_status') or 'Unfulfilled')
        order['rapidshyp_events'] = order.get('rapidshyp_events', [])
        shipped_dt = infer_shipped_datetime(order)
        delivered_dt = infer_delivered_datetime(order)
        order['shipped_at'] = shipped_dt.isoformat() if shipped_dt else order.get('shipped_at')
        order['delivered_at'] = delivered_dt.isoformat() if delivered_dt else order.get('delivered_at')
    
    return order

def run_data_sync():
    print(f"\n{'='*70}")
    print(f"[{datetime.now(TZ_INDIA).strftime('%Y-%m-%d %H:%M:%S')}] Starting Data Sync Job")
    print(f"{'='*70}\n")
    
    app = create_app()
    with app.app_context():
        config = app.config

        # --- MODIFIED: Load existing master data first ---
        existing_orders_dict = {}
        if os.path.exists(MASTER_DATA_FILE):
            print("Loading existing master data file...")
            try:
                with open(MASTER_DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_orders = json.load(f)
                existing_orders_dict = {order['id']: order for order in existing_orders}
                print(f"✓ Loaded {len(existing_orders_dict)} existing orders.\n")
            except (json.JSONDecodeError, FileNotFoundError):
                print("Could not load existing master data file. Starting fresh.")

        fetch_since_date = datetime.now(TZ_INDIA) - timedelta(days=180)
        print(f"Fetching Shopify orders created OR updated since {fetch_since_date.strftime('%Y-%m-%d')}...\n")

        params_created = {
            'status': 'any', 'limit': 250, 'created_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address'
        }
        print("Step 1: Fetching orders by created_at...")
        created_orders = get_all_shopify_orders_paginated(config, params_created)

        params_updated = {
            'status': 'any', 'limit': 250, 'updated_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address'
        }
        print("\nStep 2: Fetching orders by updated_at...")
        updated_orders = get_all_shopify_orders_paginated(config, params_updated)

        print("\nStep 3: Combining and de-duplicating orders...")
        all_recent_orders_dict = {order['id']: order for order in created_orders}
        all_recent_orders_dict.update({order['id']: order for order in updated_orders})
        
        # --- MODIFIED: Merge new data with existing data ---
        for order_id, new_order_data in all_recent_orders_dict.items():
            if order_id in existing_orders_dict:
                # Get the existing order
                existing_order = existing_orders_dict[order_id]
                # Update it with new data from Shopify
                existing_order.update(new_order_data)
                # But if 'rapidshyp_webhook_status' exists, keep it
                if 'rapidshyp_webhook_status' in existing_orders_dict[order_id]:
                    existing_order['rapidshyp_webhook_status'] = existing_orders_dict[order_id]['rapidshyp_webhook_status']
            else:
                # It's a completely new order, just add it
                existing_orders_dict[order_id] = new_order_data

        all_orders_to_process = list(existing_orders_dict.values())
        
        print(f"✓ Combined to {len(all_orders_to_process)} total unique orders\n")

        print("Step 4: Loading RapidShyp cache...")
        status_cache = load_cache()
        print(f"✓ Loaded cache with {len(status_cache)} entries\n")

        print(f"Step 5: Enriching {len(all_orders_to_process)} orders with RapidShyp tracking data (in parallel)...")
        enriched_orders = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_order = {executor.submit(enrich_order, order, status_cache, config): order for order in all_orders_to_process}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_order), start=1):
                enriched_orders.append(future.result())
                if i % 50 == 0 or i == len(all_orders_to_process):
                    print(f"    → Enriched {i}/{len(all_orders_to_process)} orders")

        print(f"✓ Enriched all {len(all_orders_to_process)} orders\n")

        print("Step 6: Saving RapidShyp cache...")
        save_cache(status_cache)
        print("✓ Cache saved\n")

        print(f"Step 7: Writing to '{MASTER_DATA_FILE}'...")
        atomic_write_json_utf8(MASTER_DATA_FILE, enriched_orders)
        print(f"✓ Saved {len(enriched_orders)} orders\n")

        print(f"{'='*70}")
        print(f"[{datetime.now(TZ_INDIA).strftime('%Y-%m-%d %H:%M:%S')}] Data Sync Job Finished Successfully")
        print(f"{'='*70}\n")

if __name__ == '__main__':
    run_data_sync()