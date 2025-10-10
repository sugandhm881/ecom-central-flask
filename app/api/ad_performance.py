from flask import Blueprint, jsonify, request, current_app
import requests
from datetime import datetime, timedelta

ad_performance_bp = Blueprint('ad_performance', __name__)

# --- Facebook Helper ---
def get_facebook_daily_spend(config, since, until):
    """Fetches daily ad spend from the Facebook Marketing API."""
    url = f"https://graph.facebook.com/v18.0/act_{config['FACEBOOK_AD_ACCOUNT_ID']}/insights"
    params = {
        'time_range': f"{{'since':'{since}','until':'{until}'}}",
        'time_increment': 1,
        'fields': 'spend,date_start',
        'access_token': config['FACEBOOK_ACCESS_TOKEN']
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json().get('data', [])
        spend_data = {item['date_start']: float(item.get('spend', 0)) for item in data}
        return spend_data
    except requests.exceptions.RequestException as e:
        print(f"Facebook API Error: {e.response.text if e.response else e}")
        return {}

# --- Shopify Helper (Simplified for this context) ---
def get_shopify_orders_for_ads(config, since):
    """
    Fetches Shopify orders from a specific date onwards.
    This is a simplified version; a real app might share this logic with the main orders endpoint.
    """
    url = f"https://{config['SHOPIFY_SHOP_URL']}/admin/api/2024-07/orders.json"
    headers = {'X-Shopify-Access-Token': config['SHOPIFY_TOKEN']}
    params = {'status': 'any', 'limit': 250, 'created_at_min': since}
    all_orders = []
    try:
        while url:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            all_orders.extend(data.get('orders', []))
            link_header = response.headers.get("link")
            url = None
            if link_header and 'rel="next"' in link_header:
                url = link_header.split(';')[0].strip('<>')
                params = {}
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Error in ad performance: {e}")
    return all_orders

def get_simulated_logistics_status(order):
    """Simulates logistics status based on order data, as in the original JS."""
    if order.get('cancelled_at'):
        return 'Cancelled'
    if 'rto' in (order.get('tags', '') or '').lower():
        return 'RTO'
    if order.get('fulfillment_status') == 'fulfilled':
        # Simulate a mix of delivered and in-transit
        return 'Delivered' if int(str(order['id'])[-2:]) < 80 else 'In-Transit'
    return 'Processing'


@ad_performance_bp.route('/get-ad-performance', methods=['GET'])
def get_ad_performance():
    """Endpoint to aggregate daily ad spend and order data."""
    since = request.args.get('since')
    until = request.args.get('until')
    if not since or not until:
        return jsonify({'error': 'A "since" and "until" date range is required.'}), 400

    config = current_app.config
    try:
        facebook_spend = get_facebook_daily_spend(config, since, until)
        shopify_orders = get_shopify_orders_for_ads(config, since)

        # Initialize daily data structure
        daily_data = {}
        start_date = datetime.strptime(since, '%Y-%m-%d').date()
        end_date = datetime.strptime(until, '%Y-%m-%d').date()
        delta = end_date - start_date
        for i in range(delta.days + 1):
            day = start_date + timedelta(days=i)
            date_str = day.strftime('%Y-%m-%d')
            daily_data[date_str] = {
                'date': date_str, 'spend': 0, 'totalOrders': 0, 'revenue': 0,
                'deliveredOrders': 0, 'cancelledOrders': 0, 'rtoOrders': 0,
                'inTransitOrders': 0, 'processingOrders': 0
            }

        # Merge Facebook spend
        for date, spend in facebook_spend.items():
            if date in daily_data:
                daily_data[date]['spend'] = spend

        # Process and merge Shopify orders
        for order in shopify_orders:
            order_date_str = datetime.fromisoformat(order['created_at']).strftime('%Y-%m-%d')
            if order_date_str in daily_data:
                slot = daily_data[order_date_str]
                status = get_simulated_logistics_status(order)
                
                slot['totalOrders'] += 1
                if status not in ['Cancelled', 'RTO']:
                    slot['revenue'] += float(order.get('total_price', 0))
                
                if status == 'Delivered': slot['deliveredOrders'] += 1
                elif status == 'RTO': slot['rtoOrders'] += 1
                elif status == 'Cancelled': slot['cancelledOrders'] += 1
                elif status == 'In-Transit': slot['inTransitOrders'] += 1
                else: slot['processingOrders'] += 1
        
        result = sorted(daily_data.values(), key=lambda x: x['date'])
        return jsonify(result)

    except Exception as e:
        print(f"Error in get-ad-performance: {e}")
        return jsonify({'error': str(e)}), 500