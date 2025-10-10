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

def run_data_sync():
    print(f"\n{'='*70}")
    print(f"[{datetime.now(TZ_INDIA).strftime('%Y-%m-%d %H:%M:%S')}] Starting Data Sync Job")
    print(f"{'='*70}\n")
    
    app = create_app()
    with app.app_context():
        config = app.config

        # Define the date range for the sync (last 90 days)
        fetch_since_date = datetime.now(TZ_INDIA) - timedelta(days=90)
        print(f"Fetching Shopify orders created OR updated since {fetch_since_date.strftime('%Y-%m-%d')}...\n")

        # Fetch orders CREATED in the last 90 days
        params_created = {
            'status': 'any',
            'limit': 250,
            'created_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address'
        }
        print("Step 1: Fetching orders by created_at...")
        created_orders = get_all_shopify_orders_paginated(config, params_created)

        # Fetch orders UPDATED in the last 90 days
        params_updated = {
            'status': 'any',
            'limit': 250,
            'updated_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address'
        }
        print("\nStep 2: Fetching orders by updated_at...")
        updated_orders = get_all_shopify_orders_paginated(config, params_updated)

        # Combine and de-duplicate
        print("\nStep 3: Combining and de-duplicating orders...")
        all_relevant_orders_dict = {order['id']: order for order in created_orders}
        all_relevant_orders_dict.update({order['id']: order for order in updated_orders})
        all_recent_orders = list(all_relevant_orders_dict.values())
        print(f"✓ Combined to {len(all_recent_orders)} unique orders\n")

        # Load RapidShyp cache
        print("Step 4: Loading RapidShyp cache...")
        status_cache = load_cache()
        print(f"✓ Loaded cache with {len(status_cache)} entries\n")

        # Enrich ALL orders with RapidShyp data
        print(f"Step 5: Enriching {len(all_recent_orders)} orders with RapidShyp tracking data...")
        for i, order in enumerate(all_recent_orders, start=1):
            # Extract AWB (tracking number) if present
            awb = next((f.get('tracking_number') for f in order.get('fulfillments', []) if f.get('tracking_number')), None)
            order['awb'] = awb

            if awb:
                # Latest raw status (cached)
                raw_status = get_raw_rapidshyp_status(awb, status_cache, config)
                order['raw_rapidshyp_status'] = raw_status

                # Full timeline for accurate shipped/delivered timestamps
                timeline = get_rapidshyp_timeline(awb, config)
                order['rapidshyp_events'] = timeline

                # Compute canonical shipped_at and delivered_at from timeline
                shipped_dt = infer_shipped_datetime(order)
                delivered_dt = infer_delivered_datetime(order)

                order['shipped_at'] = shipped_dt.isoformat() if shipped_dt else order.get('shipped_at')
                order['delivered_at'] = delivered_dt.isoformat() if delivered_dt else order.get('delivered_at')
            else:
                # Keep fields consistent for orders without AWB
                order['raw_rapidshyp_status'] = order.get('raw_rapidshyp_status', order.get('fulfillment_status') or 'Unfulfilled')
                order['rapidshyp_events'] = order.get('rapidshyp_events', [])
                
                # Try to infer dates from Shopify if no AWB
                shipped_dt = infer_shipped_datetime(order)
                delivered_dt = infer_delivered_datetime(order)
                order['shipped_at'] = shipped_dt.isoformat() if shipped_dt else order.get('shipped_at')
                order['delivered_at'] = delivered_dt.isoformat() if delivered_dt else order.get('delivered_at')

            if i % 100 == 0:
                print(f"    → Enriched {i}/{len(all_recent_orders)} orders")

        print(f"✓ Enriched all {len(all_recent_orders)} orders\n")

        # Save cache
        print("Step 6: Saving RapidShyp cache...")
        save_cache(status_cache)
        print("✓ Cache saved\n")

        # Save to master file with atomic UTF-8 write
        print(f"Step 7: Writing to '{MASTER_DATA_FILE}'...")
        atomic_write_json_utf8(MASTER_DATA_FILE, all_recent_orders)
        print(f"✓ Saved {len(all_recent_orders)} orders\n")

        print(f"{'='*70}")
        print(f"[{datetime.now(TZ_INDIA).strftime('%Y-%m-%d %H:%M:%S')}] Data Sync Job Finished Successfully")
        print(f"{'='*70}\n")

if __name__ == '__main__':
    run_data_sync()