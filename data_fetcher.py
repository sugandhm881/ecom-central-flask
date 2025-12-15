import json
import os
import tempfile
from datetime import datetime, timedelta
import pytz
import concurrent.futures
from app import create_app
from app.api.helpers import (
    get_all_shopify_orders_paginated,
    get_raw_rapidshyp_status,
    get_rapidshyp_timeline,
    save_cache,
    load_cache,
    infer_shipped_datetime,
    infer_delivered_datetime,
    fetch_docpharma_details,
    extract_docpharma_status_string
)

MASTER_DATA_FILE = 'master_order_data.json'
TZ_INDIA = pytz.timezone('Asia/Kolkata')

# -------------------------------------------------------
# Terminal-only Logging (UTF-8 safe)
def log(message):
    """Print timestamped logs live to terminal (UTF-8 safe)."""
    timestamp = datetime.now(TZ_INDIA).strftime("[%Y-%m-%d %H:%M:%S]")
    safe_message = str(message).encode("utf-8", errors="ignore").decode("utf-8")
    formatted = f"{timestamp} {safe_message}"
    print(formatted, flush=True)

# -------------------------------------------------------
def atomic_write_json_utf8(path, data):
    """Atomically write JSON data to a file with UTF-8 encoding."""
    dir_ = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Verify read
        with open(tmp_path, 'r', encoding='utf-8') as v:
            json.load(v)
        os.replace(tmp_path, path)
        log(f"✓ File validated and saved successfully ({path})")
    except Exception as e:
        log(f"✗ Error during atomic write: {e}")
        try:
            os.remove(tmp_path)
        except:
            pass
        raise

def enrich_order(order, status_cache, config):
    """
    Enriches a single order with RapidShyp OR DocPharma data (thread-safe).
    """
    # Try to find an AWB in fulfillments
    awb = next((f.get('tracking_number') for f in order.get('fulfillments', []) if f.get('tracking_number')), None)
    order['awb'] = awb

    raw_status = None
    timeline = []

    # 1. Try Fetching from RapidShyp
    if awb:
        # returns None if 400 (Bad Request), or a string like "Delivered", "Status Not Available"
        raw_status = get_raw_rapidshyp_status(awb, status_cache, config)
        
        # Only fetch timeline if status looks valid
        if raw_status and raw_status not in ["Status Not Available", "API Error or Timeout"]:
            timeline = get_rapidshyp_timeline(awb, config)

    # 2. Fallback to DocPharma if RapidShyp failed
    # We check if raw_status is None (from 400 error) or "Status Not Available"
    if not raw_status or raw_status in ["Status Not Available", "API Error or Timeout"]:
        # Query DocPharma using the Order Name (e.g. #TE25-6613)
        # This is more reliable than AWB for DocPharma
        order_name = order.get('name', '').replace('#', '')
        if order_name:
            doc_data = fetch_docpharma_details(order_name, config)
            
            if doc_data:
                # Save full data for frontend/logic
                order['docpharma_data'] = doc_data
                
                # Extract precise status (e.g. RTO_DELIVERED)
                extracted_status = extract_docpharma_status_string(doc_data)
                
                if extracted_status:
                    raw_status = extracted_status
                    # Create a synthetic timeline event so charts work
                    timeline = [{
                        'status': raw_status,
                        'timestamp': datetime.now(TZ_INDIA).isoformat(),
                        'location': 'DocPharma API'
                    }]
    
    # 3. Apply Final Data to Order
    # If both failed, fallback to Shopify status
    if not raw_status:
        raw_status = order.get('fulfillment_status') or 'Unfulfilled'

    order['raw_rapidshyp_status'] = raw_status
    order['rapidshyp_events'] = timeline
    
    # Infer dates based on whatever timeline we found
    shipped_dt = infer_shipped_datetime(order)
    delivered_dt = infer_delivered_datetime(order)
    
    order['shipped_at'] = shipped_dt.isoformat() if shipped_dt else order.get('shipped_at')
    order['delivered_at'] = delivered_dt.isoformat() if delivered_dt else order.get('delivered_at')
    
    return order

def run_data_sync():
    log("=" * 70)
    log("Starting Data Sync Job")

    app = create_app()
    with app.app_context():
        config = app.config

        # Load existing master data if available
        existing_orders_dict = {}
        if os.path.exists(MASTER_DATA_FILE):
            log("Loading existing master data file...")
            try:
                with open(MASTER_DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_orders = json.load(f)
                existing_orders_dict = {str(order['id']): order for order in existing_orders}
                log(f"✓ Loaded {len(existing_orders_dict)} existing orders.")
            except (json.JSONDecodeError, FileNotFoundError):
                log("Could not load existing master data file. Starting fresh.")

        fetch_since_date = datetime.now(TZ_INDIA) - timedelta(days=180)
        log(f"Fetching Shopify orders created OR updated since {fetch_since_date.strftime('%Y-%m-%d')}")

        params_created = {
            'status': 'any', 'limit': 250, 'created_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address,updated_at'
        }
        log("Step 1: Fetching orders by created_at...")
        created_orders = get_all_shopify_orders_paginated(config, params_created)

        params_updated = {
            'status': 'any', 'limit': 250, 'updated_at_min': fetch_since_date.isoformat(),
            'fields': 'id,name,created_at,total_price,fulfillments,note_attributes,source_name,referring_site,cancelled_at,fulfillment_status,line_items,email,shipping_address,updated_at'
        }
        log("Step 2: Fetching orders by updated_at...")
        updated_orders = get_all_shopify_orders_paginated(config, params_updated)

        log("Step 3: Combining and de-duplicating orders...")
        # Use str(id) for consistency
        all_recent_orders_dict = {str(order['id']): order for order in created_orders}
        all_recent_orders_dict.update({str(order['id']): order for order in updated_orders})

        # Merge with existing data
        for order_id, new_order_data in all_recent_orders_dict.items():
            if order_id in existing_orders_dict:
                existing_order = existing_orders_dict[order_id]
                existing_order.update(new_order_data)
                # Preserve webhook status if it exists
                if 'rapidshyp_webhook_status' in existing_orders_dict[order_id]:
                    existing_order['rapidshyp_webhook_status'] = existing_orders_dict[order_id]['rapidshyp_webhook_status']
                # Preserve DocPharma data if not present in new fetch
                if 'docpharma_data' in existing_orders_dict[order_id]:
                    existing_order['docpharma_data'] = existing_orders_dict[order_id]['docpharma_data']
            else:
                existing_orders_dict[order_id] = new_order_data

        all_orders_to_process = list(existing_orders_dict.values())
        log(f"✓ Combined to {len(all_orders_to_process)} total unique orders")

        log("Step 4: Loading RapidShyp cache...")
        status_cache = load_cache()
        log(f"✓ Loaded cache with {len(status_cache)} entries")

        log(f"Step 5: Enriching {len(all_orders_to_process)} orders with RapidShyp/DocPharma data (parallel)...")
        
        enriched_orders = []
        # Use ThreadPool to speed up network requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_order = {executor.submit(enrich_order, order, status_cache, config): order for order in all_orders_to_process}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_order), start=1):
                try:
                    data = future.result()
                    enriched_orders.append(data)
                except Exception as exc:
                    log(f"✗ Order generated an exception: {exc}")
                
                if i % 50 == 0 or i == len(all_orders_to_process):
                    log(f"→ Enriched {i}/{len(all_orders_to_process)} orders")

        log(f"✓ Enriched all {len(all_orders_to_process)} orders")

        log("Step 6: Saving RapidShyp cache...")
        # Passing full dict to updated save_cache function
        save_cache(status_cache)
        log("✓ Cache saved")

        log(f"Step 7: Writing to '{MASTER_DATA_FILE}'...")
        atomic_write_json_utf8(MASTER_DATA_FILE, enriched_orders)
        log(f"✓ Saved {len(enriched_orders)} orders")

    log("Data Sync Job Finished Successfully")
    log("=" * 70)


if __name__ == '__main__':
    run_data_sync()