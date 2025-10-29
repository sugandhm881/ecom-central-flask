from flask import Blueprint, request, jsonify, current_app
import json
import os
import threading
import traceback # Import traceback for detailed error logging

webhook_bp = Blueprint('webhook', __name__)

MASTER_DATA_FILE = 'master_order_data.json'
file_lock = threading.Lock()

@webhook_bp.route('/rapidshyp', methods=['POST'])
def handle_rapidshyp_webhook():
    """
    Handles incoming webhook notifications from RapidShyp with detailed logging.
    """
    print("\n--- [Webhook Received] ---") # Log when a request hits the endpoint
    data = request.get_json()

    if not data:
        print("[Webhook Error] No JSON payload received.")
        return jsonify({'error': 'No JSON payload received'}), 400

    print(f"[Webhook Data] Received payload: {json.dumps(data, indent=2)}") # Log the received data

    if 'records' not in data:
        print("[Webhook Error] Invalid payload format: 'records' key missing.")
        return jsonify({'error': 'Invalid payload format'}), 400

    updated_count = 0
    try:
        for record in data.get('records', []):
            order_id = record.get('seller_order_id')
            shipment_details = record.get('shipment_details', [{}])[0]
            shipment_status = shipment_details.get('shipment_status')
            awb = shipment_details.get('awb')

            print(f"[Webhook Processing] Record - Order ID: {order_id}, Status: {shipment_status}, AWB: {awb}")

            if not order_id or not shipment_status:
                print(f"[Webhook Warning] Skipping record due to missing order_id or shipment_status.")
                continue

            updated = update_master_order_file(order_id, shipment_status, awb)
            if updated:
                updated_count += 1

        print(f"[Webhook Result] Successfully processed payload. Updated {updated_count} order(s).")
        return jsonify({'status': 'success'}), 200

    except Exception as e:
        print(f"--- [CRITICAL WEBHOOK ERROR] ---")
        # Log the full traceback for detailed debugging
        print(traceback.format_exc())
        return jsonify({'error': 'An internal server error occurred.'}), 500

def update_master_order_file(order_id_from_webhook, new_status, awb):
    """
    Updates the master order data file with the new status from the webhook.
    Returns True if update was successful, False otherwise.
    """
    print(f"[Webhook Update] Attempting to update order: {order_id_from_webhook}")
    with file_lock:
        if not os.path.exists(MASTER_DATA_FILE):
            print(f"[Webhook Update Error] Master data file '{MASTER_DATA_FILE}' not found.")
            return False

        all_orders = []
        try:
            with open(MASTER_DATA_FILE, 'r', encoding='utf-8') as f:
                all_orders = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
             print(f"[Webhook Update Error] Could not read master data file: {e}")
             return False
        except UnicodeDecodeError:
             print(f"[Webhook Update Warning] UnicodeDecodeError reading master file. Retrying with errors='replace'.")
             try:
                 with open(MASTER_DATA_FILE, 'r', encoding='utf-8', errors='replace') as f:
                     all_orders = json.load(f)
             except Exception as e:
                 print(f"[Webhook Update Error] Could not read master data file even with replace: {e}")
                 return False

        order_found = False
        for order in all_orders:
            # Check for potential mismatch (e.g., with or without '#')
            order_name_in_file = order.get('name')
            if order_name_in_file == order_id_from_webhook or \
               (order_name_in_file and order_name_in_file.lstrip('#') == order_id_from_webhook) or \
               (order_name_in_file and '#' + order_id_from_webhook == order_name_in_file):

                print(f"[Webhook Update] Found matching order: {order_name_in_file}. Updating status to '{new_status}'.")
                order['rapidshyp_webhook_status'] = new_status
                if awb and not order.get('awb'): # Update AWB if missing
                    order['awb'] = awb
                order_found = True
                break # Stop searching once found

        if not order_found:
            print(f"[Webhook Update Warning] Order ID '{order_id_from_webhook}' not found in master data file.")
            return False

        # Write the updated data back atomically (using a temporary file)
        try:
            temp_file_path = MASTER_DATA_FILE + ".tmp"
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                json.dump(all_orders, f, indent=4)
            os.replace(temp_file_path, MASTER_DATA_FILE) # Atomic replace
            print(f"[Webhook Update] Successfully updated master data file for order {order_id_from_webhook}.")
            return True
        except Exception as e:
            print(f"[Webhook Update Error] Failed to write updated master data file: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except: pass
            return False