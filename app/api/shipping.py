from flask import Blueprint, request, jsonify, current_app, Response
import requests
from ..auth import token_required
import json
import time

shipping_bp = Blueprint('shipping', __name__)

@shipping_bp.route('/create-shipment', methods=['POST'])
@token_required
def create_shipment():
    data = request.get_json()
    shopify_order_id = data.get('orderId')
    config = current_app.config
    if not shopify_order_id:
        return jsonify({'error': 'Shopify Order ID is required.'}), 400

    try:
        # 1. Fetch full order details from Shopify
        shopify_url = f"https://{config['SHOPIFY_SHOP_URL']}/admin/api/2024-07/orders/{shopify_order_id}.json"
        headers = {'X-Shopify-Access-Token': config['SHOPIFY_TOKEN']}
        response = requests.get(shopify_url, headers=headers)
        response.raise_for_status()
        order = response.json()['order']

        # 2. Construct the payload EXACTLY as per the API's requirements
        shipping_address = order.get('shipping_address', {}) or {}
        rapidshyp_payload = {
            "order_id": order['name'].replace('#', ''),
            "shipping_customer_name": f"{shipping_address.get('first_name', '')} {shipping_address.get('last_name', '')}".strip(),
            "shipping_address": shipping_address.get('address1', ''),
            "shipping_city": shipping_address.get('city', ''),
            "shipping_pincode": shipping_address.get('zip', ''),
            "shipping_state": shipping_address.get('province', ''),
            "shipping_email": order.get('email', ''),
            "shipping_phone": shipping_address.get('phone', ''),
            
            # --- THIS IS THE FIX ---
            # The key is changed from 'order_items' to 'orderItems'
            "orderItems": [{
                "sku": item.get('sku', f'SKU-{item["id"]}'),
                "name": item.get('name', 'Product Name'),
                "quantity": str(item.get('quantity', 1)),
                "price": str(item.get('price', 0)),
            } for item in order.get('line_items', [])],
            # --- END OF FIX ---

            "payment_mode": "Prepaid" if order.get('financial_status') == 'paid' else "COD",
            "total_amount": float(order.get('total_price', 0)),
            "weight": "0.5",
            "sub_total": float(order.get('subtotal_price', 0))
        }

        # 3. Call the correct 'create_order' endpoint
        rapidshyp_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/create_order"
        rs_headers = {
            'rapidshyp-token': config['RAPIDSHYP_API_KEY'],
            'Content-Type': 'application/json'
        }
        
        print(f"\n--- [RapidShyp CREATE SHIPMENT DEBUG] ---")
        print(f"Calling URL: {rapidshyp_url}")
        print(f"Payload: {json.dumps(rapidshyp_payload, indent=2)}")
        
        rs_response = requests.post(rapidshyp_url, json=rapidshyp_payload, headers=rs_headers)
        
        print(f"Status Code: {rs_response.status_code}")
        print(f"Response Body: {rs_response.text}")
        print("--- END OF DEBUG ---\n")
        rs_response.raise_for_status()
        rs_data = rs_response.json()

        # 4. Extract the URLs and return them to the frontend
        shipment_data = rs_data.get('data', [{}])[0]
        return jsonify({
            'success': True,
            'newStatus': 'Processing',
            'awb': shipment_data.get('awb_code'),
            'courier': shipment_data.get('courier_name'),
            'label_url': shipment_data.get('label_url'), # Assuming these keys exist
            'invoice_url': shipment_data.get('invoice_url') # Assuming these keys exist
        })

    except requests.exceptions.HTTPError as e:
        return jsonify({'error': f"RapidShyp API Error: {e.response.status_code} - {e.response.text}"}), e.response.status_code
    except Exception as e:
        print(f"Error creating shipment: {e}")
        return jsonify({'error': f"An unexpected error occurred: {e}"}), 500


@shipping_bp.route('/get-shipping-label', methods=['GET'])
@token_required
def get_shipping_label():
    awb = request.args.get('awb')
    config = current_app.config
    if not awb: return jsonify({'error': 'AWB number is required.'}), 400
    try:
        track_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
        headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
        response = requests.post(track_url, headers=headers, json={'awb': awb})
        response.raise_for_status()
        data = response.json()
        label_url = data.get('records', [{}])[0].get('shipment_details', [{}])[0].get('label_url')
        if not label_url:
            return jsonify({'error': 'Label URL not found in RapidShyp response.'}), 404
        pdf_response = requests.get(label_url); pdf_response.raise_for_status()
        return Response(pdf_response.content, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename=label_{awb}.pdf'})
    except Exception as e:
        print(f"Error fetching label for AWB {awb}: {e}")
        return jsonify({'error': f"Failed to fetch label: {e}"}), 500

@shipping_bp.route('/get-shipping-invoice', methods=['GET'])
@token_required
def get_shipping_invoice():
    awb = request.args.get('awb')
    order_id = request.args.get('orderId')
    config = current_app.config
    if not awb: return jsonify({'error': 'AWB number is required.'}), 400
    try:
        track_url = "https://api.rapidshyp.com/rapidshyp/apis/v1/track_order"
        headers = {"rapidshyp-token": config.get('RAPIDSHYP_API_KEY'), "Content-Type": "application/json"}
        response = requests.post(track_url, headers=headers, json={'awb': awb})
        response.raise_for_status()
        data = response.json()
        invoice_url = data.get('records', [{}])[0].get('shipment_details', [{}])[0].get('invoice_url')
        if not invoice_url:
            return jsonify({'error': 'Invoice URL not found in RapidShyp response.'}), 404
        pdf_response = requests.get(invoice_url); pdf_response.raise_for_status()
        filename = f'invoice_{order_id.replace("#", "")}.pdf' if order_id else f'invoice_{awb}.pdf'
        return Response(pdf_response.content, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={filename}'})
    except Exception as e:
        print(f"Error fetching invoice for AWB {awb}: {e}")
        return jsonify({'error': f"Failed to fetch invoice: {e}"}), 500