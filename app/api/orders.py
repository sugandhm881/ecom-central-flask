from flask import Blueprint, jsonify, current_app
from datetime import datetime, timedelta
from .amazon import fetch_amazon_orders
# --- THIS IS THE FIX ---
from .helpers import get_all_shopify_orders_paginated
# --- END OF FIX ---
from ..auth import token_required

orders_bp = Blueprint('orders', __name__)

def normalize_shopify_order(order):
    status = "New" if not order.get('fulfillment_status') else "Shipped" if order.get('fulfillment_status') == 'fulfilled' else "Processing"
    if order.get('cancelled_at'): status = "Cancelled"
    awb = next((f.get('tracking_number') for f in order.get('fulfillments', []) if f.get('tracking_number')), None)
    if awb and status == "New": status = "Processing"
    refunds = sum(float(t.get('amount', 0)) for r in order.get('refunds', []) for t in r.get('transactions', []) if t.get('kind') == 'refund' and t.get('status') == 'success')
    net_total = float(order.get('total_price', 0)) - refunds
    address = order.get('shipping_address', {}) or {}
    customer_name = f"{address.get('first_name', '')} {address.get('last_name', '')}".strip() or 'N/A'
    address_str = f"{address.get('address1', '')}, {address.get('city', '')}".strip(', ')
    return {
        "platform": "Shopify", "id": order['name'], "originalId": order['id'],
        "date": datetime.fromisoformat(order['created_at']).strftime('%Y-%m-%d'),
        "name": customer_name, "total": net_total, "status": status,
        "items": [{"name": i.get('name', 'N/A'), "sku": i.get('sku', 'N/A'), "qty": i.get('quantity', 0)} for i in order.get('line_items', [])],
        "address": address_str or 'No address',
        "paymentMethod": 'Prepaid' if order.get('financial_status') == 'paid' else 'COD',
        "awb": awb
    }

@orders_bp.route('/get-orders', methods=['GET'])
@token_required
def get_orders():
    config = current_app.config
    try:
        sixty_days_ago = (datetime.now() - timedelta(days=60)).isoformat()
        shopify_params = {
            'status': 'any', 'limit': 250,
            'created_at_min': sixty_days_ago,
            'fields': 'id,name,created_at,total_price,financial_status,fulfillment_status,cancelled_at,shipping_address,line_items,tags,refunds,fulfillments'
        }
        print("\n[Orders Endpoint] Fetching all paginated Shopify orders...")
        shopify_orders_raw = get_all_shopify_orders_paginated(config, shopify_params)
        shopify_orders = [normalize_shopify_order(order) for order in shopify_orders_raw]
        amazon_orders = fetch_amazon_orders(config)
        all_orders = sorted(shopify_orders + amazon_orders, key=lambda x: x['date'], reverse=True)
        return jsonify(all_orders)
    except Exception as e:
        print(f"CRITICAL ERROR in get-orders: {e}")
        return jsonify({"error": str(e)}), 500