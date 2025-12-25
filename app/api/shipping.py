from flask import Blueprint, request, jsonify, current_app, Response
import requests
from ..auth import token_required
import json
import re
import time
import os
from datetime import datetime

shipping_bp = Blueprint('shipping', __name__)

# --- FILE PATHS ---
ORDER_CACHE_FILE = 'order_shipment_cache.json'
AWB_CACHE_FILE = 'awb_assignment_cache.json'
MASTER_LOG_FILE = 'master_api_log.json'

# --- JSON UTILS ---
def load_json_file(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return {}

def save_json_file(filepath, data):
    try:
        with open(filepath, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"Cache Save Failed ({filepath}): {e}")

# --- MASTER LOGGER ---
def log_to_master(action, payload, response_data, status_code=200):
    """Appends API interactions to a master log file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status_code": status_code,
        "payload": payload,
        "response": response_data
    }
    
    try:
        # Load existing log or create new list
        if os.path.exists(MASTER_LOG_FILE):
            with open(MASTER_LOG_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                    if not isinstance(logs, list): logs = []
                except: logs = []
        else:
            logs = []
        
        logs.append(entry)
        
        # Save back
        with open(MASTER_LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=4)
            
    except Exception as e:
        print(f"[Master Log] Failed to save: {e}")

# --- SPECIFIC CACHES ---
def get_cached_shipment_id(order_id):
    return load_json_file(ORDER_CACHE_FILE).get(str(order_id))

def save_cached_shipment_id(order_id, shipment_id):
    if not order_id or not shipment_id: return
    cache = load_json_file(ORDER_CACHE_FILE)
    if str(order_id) not in cache:
        cache[str(order_id)] = shipment_id
        save_json_file(ORDER_CACHE_FILE, cache)

def get_cached_awb_data(shipment_id):
    return load_json_file(AWB_CACHE_FILE).get(str(shipment_id))

def save_cached_awb_data(shipment_id, response_data):
    if not shipment_id or not response_data: return
    cache = load_json_file(AWB_CACHE_FILE)
    if str(shipment_id) not in cache:
        cache[str(shipment_id)] = response_data
        save_json_file(AWB_CACHE_FILE, cache)

# --- HELPERS ---
def scan_shipments(s_list, ids_to_check):
    for s in s_list:
        oid = str(s.get('order_id') or s.get('orderId') or '')
        sid = str(s.get('seller_order_id') or '')
        if oid in ids_to_check or sid in ids_to_check:
            return s.get('shipment_id') or s.get('shipmentId')
    return None

def find_shipment_id_robust(config, order_id):
    cached_id = get_cached_shipment_id(order_id)
    if cached_id: return cached_id

    if not order_id: return None
    headers = {'rapidshyp-token': config['RAPIDSHYP_API_KEY'], 'Content-Type': 'application/json'}
    input_id = str(order_id)
    ids_to_check = [input_id, input_id.replace('#', '')] 
    
    try:
        shopify_url = f"https://{config['SHOPIFY_SHOP_URL']}/admin/api/2024-07/orders/{order_id}.json"
        sh_headers = {'X-Shopify-Access-Token': config['SHOPIFY_TOKEN']}
        sh_res = requests.get(shopify_url, headers=sh_headers)
        if sh_res.status_code == 200:
            o = sh_res.json().get('order', {})
            ids_to_check.append(str(o.get('id')))
            ids_to_check.append(str(o.get('name')).replace('#', ''))
            ids_to_check.append(str(o.get('name')))
    except: pass

    ids_to_check = list(set([i for i in ids_to_check if i]))
    shipments_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/shipments"
    track_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
    
    for attempt in range(3):
        try:
            filter_val = ids_to_check[1] if len(ids_to_check) > 1 else ids_to_check[0]
            s_res = requests.post(shipments_url, headers=headers, json={"filter": {"order_id": filter_val}})
            if s_res.status_code == 200:
                sid = scan_shipments(s_res.json().get('data', []), ids_to_check)
                if sid: 
                    save_cached_shipment_id(order_id, sid)
                    return sid
        except: pass

        for tid in ids_to_check:
            try:
                for key in ['order_id', 'seller_order_id']:
                    res = requests.post(track_url, headers=headers, json={key: tid})
                    if res.status_code == 200:
                        rec = res.json().get('records', [])
                        if rec and rec[0].get('shipment_details'):
                            sid = rec[0]['shipment_details'][0].get('shipment_id')
                            if sid:
                                save_cached_shipment_id(order_id, sid)
                                return sid
            except: pass
        if attempt < 2: time.sleep(1.5)
    return None

# --- STATUS CHECK ---
@shipping_bp.route('/get-shipment-status', methods=['POST'])
@token_required
def get_shipment_status():
    data = request.get_json()
    order_id = data.get('orderId')
    config = current_app.config
    shipment_id = find_shipment_id_robust(config, order_id)
    
    awb_data = get_cached_awb_data(shipment_id) if shipment_id else None
    
    response_payload = {
        'shipmentId': shipment_id, 
        'awbAssigned': bool(awb_data),
        'awbData': awb_data
    }
    
    # Log status check (optional, can be noisy)
    # log_to_master("get_shipment_status", data, response_payload)
    
    return jsonify(response_payload)

# --- STEP 1: APPROVE ORDER ---
@shipping_bp.route('/approve-order', methods=['POST'])
@token_required
def approve_order():
    data = request.get_json()
    shopify_numeric_id = data.get('orderId') 
    store_name = "The Element"
    config = current_app.config
    
    if not shopify_numeric_id: return jsonify({'error': 'Order ID is required.'}), 400

    cached_id = get_cached_shipment_id(shopify_numeric_id)
    if cached_id:
        return jsonify({'success': True, 'message': 'Cached.', 'shipmentId': cached_id})

    try:
        shopify_url = f"https://{config['SHOPIFY_SHOP_URL']}/admin/api/2024-07/orders/{shopify_numeric_id}.json"
        shopify_headers = {'X-Shopify-Access-Token': config['SHOPIFY_TOKEN']}
        requests.get(shopify_url, headers=shopify_headers) 
        
        headers = { 'rapidshyp-token': config['RAPIDSHYP_API_KEY'], 'Content-Type': 'application/json' }
        approve_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/approve_orders"
        payload = { "order_id": [str(shopify_numeric_id)], "store_name": store_name }
        
        response = requests.post(approve_url, json=payload, headers=headers)
        
        try:
            resp_json = response.json()
        except:
            resp_json = {"text": response.text}

        log_to_master("approve_order", payload, resp_json, response.status_code)

        shipment_id = ""
        is_success = False
        rj = resp_json if isinstance(resp_json, dict) else {}

        if response.status_code == 200:
            if rj.get('status') is True or rj.get('status') == 'success':
                is_success = True
                data_list = rj.get('data', []) or rj.get('order_list', [])
                if data_list and len(data_list) > 0:
                    if data_list[0].get('shipment'):
                         shipments = data_list[0].get('shipment')
                         if shipments: shipment_id = shipments[0].get('shipment_id')
                    else:
                        shipment_id = data_list[0].get('shipment_id')
            elif "already approved" in str(rj.get('message', '')).lower() or "already approved" in str(rj.get('remark', '')).lower():
                is_success = True 
                shipment_id = find_shipment_id_robust(config, shopify_numeric_id)

        if is_success:
            if shipment_id: save_cached_shipment_id(shopify_numeric_id, shipment_id)
            return jsonify({'success': True, 'message': 'Approved.', 'shipmentId': shipment_id})
        
        return jsonify({'error': f"Failed: {rj.get('message') or response.text}"}), response.status_code

    except Exception as e:
        log_to_master("approve_order_error", data, {"error": str(e)}, 500)
        return jsonify({'error': str(e)}), 500

# --- STEP 2: ASSIGN AWB ---
@shipping_bp.route('/assign-awb', methods=['POST'])
@token_required
def assign_awb():
    data = request.get_json()
    shipment_id = data.get('shipmentId')
    order_id = data.get('orderId') 
    courier_code = data.get('courierCode')
    config = current_app.config
    headers = {'rapidshyp-token': config['RAPIDSHYP_API_KEY'], 'Content-Type': 'application/json'}

    if not shipment_id and order_id:
        shipment_id = find_shipment_id_robust(config, order_id)

    if not shipment_id: 
        return jsonify({'error': 'Shipment ID not found.'}), 400

    # 1. CHECK AWB CACHE
    cached_awb = get_cached_awb_data(shipment_id)
    if cached_awb:
        return jsonify(cached_awb)

    try:
        url = "https://api.rapidshyp.com/rapidshyp/apis/v1/assign_awb"
        payload = {"shipment_id": shipment_id}
        if courier_code: payload["courier_code"] = courier_code
        if "courier_code" not in payload: payload["courier_code"] = ""
            
        response = requests.post(url, json=payload, headers=headers)
        
        try:
            resp_json = response.json()
        except:
            resp_json = {"text": response.text}

        log_to_master("assign_awb", payload, resp_json, response.status_code)
        
        if response.status_code == 200:
            rj = resp_json
            if rj.get('status') == 'SUCCESS' or rj.get('awb'):
                if order_id: save_cached_shipment_id(order_id, shipment_id)
                success_data = {
                    'success': True, 
                    'awb': rj.get('awb'), 
                    'courier': rj.get('courier_name'),
                    'courier_code': rj.get('courier_code'),
                    'shipment_id': rj.get('shipment_id'),
                    'label': rj.get('label') 
                }
                save_cached_awb_data(shipment_id, success_data)
                return jsonify(success_data)
            else:
                return jsonify({'error': f"Error: {rj.get('remarks')}"}), 400
        
        return jsonify({'error': f"API Error: {response.text}"}), response.status_code
    except Exception as e:
        log_to_master("assign_awb_error", data, {"error": str(e)}, 500)
        return jsonify({'error': str(e)}), 500

# --- CANCEL ORDER ---
@shipping_bp.route('/cancel-order', methods=['POST'])
@token_required
def cancel_order():
    data = request.get_json()
    order_id = data.get('orderId')   # RapidShyp Order ID
    config = current_app.config

    if not order_id:
        return jsonify({'error': 'orderId is required'}), 400

    try:
        url = "https://api.rapidshyp.com/rapidshyp/apis/v1/cancel_order"
        headers = {
            'rapidshyp-token': config['RAPIDSHYP_API_KEY'],
            'Content-Type': 'application/json'
        }

        payload = {
            "orderId": str(order_id),
            "storeName": "The Element"   # 🔒 FIXED
        }

        response = requests.post(url, headers=headers, json=payload)

        try:
            resp_json = response.json()
        except:
            resp_json = {"text": response.text}

        log_to_master("cancel_order", payload, resp_json, response.status_code)

        if response.status_code == 200 and resp_json.get('status') is True:
            return jsonify({
                'success': True,
                'remarks': resp_json.get('remarks', 'Order canceled successfully.')
            })

        return jsonify({
            'error': resp_json.get('remarks', 'Cancel failed')
        }), response.status_code

    except Exception as e:
        log_to_master("cancel_order_error", data, {"error": str(e)}, 500)
        return jsonify({'error': str(e)}), 500

# --- GENERATE LABEL (FIXED) ---
@shipping_bp.route('/generate-label', methods=['POST'])
@token_required
def generate_label():
    data = request.get_json()
    shipment_id = data.get('shipmentId')
    config = current_app.config

    if not shipment_id: return jsonify({'error': 'Shipment ID required.'}), 400

    # Check AWB Cache first for label
    cached = get_cached_awb_data(shipment_id)
    if cached and cached.get('label'):
        return jsonify({'success': True, 'labelUrl': cached.get('label')})

    try:
        url = "https://api.rapidshyp.com/rapidshyp/apis/v1/generate_label"
        headers = {'rapidshyp-token': config['RAPIDSHYP_API_KEY'], 'Content-Type': 'application/json'}
        payload = {"shipmentId": [str(shipment_id)]}
        
        response = requests.post(url, json=payload, headers=headers)
        
        try:
            res_data = response.json()
        except:
            res_data = {"text": response.text}

        log_to_master("generate_label", payload, res_data, response.status_code)
        
        label_url = None
        
        # 1. Check Root Level 'label_url' (Matches your logs)
        if res_data.get('label_url'):
            label_url = res_data.get('label_url')
            
        # 2. Check 'labelData' List (Fallback from docs)
        elif res_data.get('labelData') and len(res_data['labelData']) > 0:
            label_url = res_data['labelData'][0].get('labelURL')
            
        if label_url:
            # Update cache
            if cached:
                cached['label'] = label_url
                save_cached_awb_data(shipment_id, cached)
            # Create new cache entry if missing
            else:
                save_cached_awb_data(shipment_id, {'label': label_url})
            
            return jsonify({'success': True, 'labelUrl': label_url})
            
        return jsonify({'error': 'Label URL missing in response.'}), 400
    except Exception as e:
        log_to_master("generate_label_error", data, {"error": str(e)}, 500)
        return jsonify({'error': str(e)}), 500

# --- UTILS (Logged) ---
@shipping_bp.route('/get-shipping-label', methods=['GET'])
@token_required
def get_shipping_label():
    awb = request.args.get('awb')
    config = current_app.config
    if not awb: return jsonify({'error': 'AWB required.'}), 400
    
    try:
        headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
        track_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
        track_res = requests.post(track_url, headers=headers, json={'awb': awb})
        
        label_url = None
        shipment_id = None
        if track_res.status_code == 200:
            data = track_res.json()
            if data.get('records'):
                details = data['records'][0].get('shipment_details', [])
                if details: 
                    label_url = details[0].get('label_url') or details[0].get('labelURL')
                    shipment_id = details[0].get('shipment_id')

        if not label_url and shipment_id:
            gen_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/generate_label"
            payload = {"shipmentId": [shipment_id]}
            gen_res = requests.post(gen_url, headers=headers, json=payload)
            
            # Log generation
            try: gen_json = gen_res.json() 
            except: gen_json = {}
            log_to_master("get_shipping_label_fallback", payload, gen_json, gen_res.status_code)

            if gen_res.status_code == 200:
                if gen_json.get('label_url'): label_url = gen_json.get('label_url')
                elif gen_json.get('labelData'): label_url = gen_json['labelData'][0].get('labelURL')

        if label_url: return jsonify({'success': True, 'url': label_url})
        return jsonify({'error': 'Label not found.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@shipping_bp.route('/get-shipping-invoice', methods=['GET'])
@token_required
def get_shipping_invoice():
    awb = request.args.get('awb')
    order_id = request.args.get('orderId') 
    config = current_app.config
    if not awb: return jsonify({'error': 'AWB required.'}), 400
    
    try:
        headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
        track_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
        response = requests.post(track_url, headers=headers, json={'awb': awb})
        
        invoice_url = None
        label_url_fallback = None
        if response.status_code == 200:
            data = response.json()
            if data.get('records'):
                details = data['records'][0].get('shipment_details', [])
                if details:
                    invoice_url = details[0].get('invoice_url') or details[0].get('invoiceURL')
                    label_url_fallback = details[0].get('label_url') or details[0].get('labelURL')
        
        if not invoice_url: invoice_url = label_url_fallback
        if invoice_url: return jsonify({'success': True, 'url': invoice_url})
        return jsonify({'error': 'Invoice not found.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@shipping_bp.route('/schedule-pickup', methods=['POST'])
@token_required
def schedule_pickup():
    data = request.get_json()
    order_id = data.get('orderId')
    shipment_id = data.get('shipmentId')
    config = current_app.config

    # 1️⃣ Resolve shipment_id if only orderId is sent
    if not shipment_id and order_id:
        shipment_id = find_shipment_id_robust(config, order_id)

    if not shipment_id:
        return jsonify({'error': 'shipmentId not found'}), 400

    # 2️⃣ Read AWB from cache
    cached_awb = get_cached_awb_data(shipment_id)

    if not cached_awb or not cached_awb.get('awb'):
        return jsonify({
            'error': 'AWB not found in cache. Assign AWB before scheduling pickup.'
        }), 400

    awb = cached_awb.get('awb')

    try:
        url = "https://api.rapidshyp.com/rapidshyp/apis/v1/schedule_pickup"
        headers = {
            'rapidshyp-token': config['RAPIDSHYP_API_KEY'],
            'Content-Type': 'application/json'
        }

        payload = {
            "shipment_id": shipment_id,
            "awb": awb
        }

        response = requests.post(url, headers=headers, json=payload)

        try:
            resp_json = response.json()
        except:
            resp_json = {"text": response.text}

        log_to_master("schedule_pickup", payload, resp_json, response.status_code)

        if response.status_code == 200 and resp_json.get('status') == "SUCCESS":
            return jsonify({
                'success': True,
                'shipmentId': resp_json.get('shipmentId'),
                'orderId': resp_json.get('orderId'),
                'awb': resp_json.get('awb'),
                'courierCode': resp_json.get('courierCode'),
                'courierName': resp_json.get('courierName'),
                'routingCode': resp_json.get('routingCode'),
                'rtoRoutingCode': resp_json.get('rtoRoutingCode'),
                'remarks': resp_json.get('remarks')
            })

        return jsonify({
            'error': resp_json.get('remarks', 'Pickup scheduling failed')
        }), response.status_code

    except Exception as e:
        log_to_master("schedule_pickup_error", data, {"error": str(e)}, 500)
        return jsonify({'error': str(e)}), 500
