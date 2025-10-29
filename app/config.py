import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('JWT_SECRET') or 'you-should-really-change-this'
    
    # Shopify Credentials
    SHOPIFY_TOKEN = os.environ.get('SHOPIFY_TOKEN')
    SHOPIFY_SHOP_URL = os.environ.get('SHOPIFY_SHOP_URL')

    # Facebook Ads Credentials
    FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
    FACEBOOK_AD_ACCOUNT_ID = os.environ.get('FACEBOOK_AD_ACCOUNT_ID')

    # --- AMAZON KEYS ---
    AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
    AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
    AWS_REGION = os.environ.get('AWS_REGION')
    LWA_CLIENT_ID = os.environ.get('LWA_CLIENT_ID')
    LWA_CLIENT_SECRET = os.environ.get('LWA_CLIENT_SECRET')
    REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN')
    MARKETPLACE_ID = os.environ.get('MARKETPLACE_ID')
    BASE_URL = os.environ.get('BASE_URL', 'https://sellingpartnerapi-eu.amazon.com')

    # RapidShyp Credentials
    RAPIDSHYP_API_KEY = os.environ.get('RAPIDSHYP_API_KEY')
    
    # App User Credentials (for login)
    APP_USER_EMAIL = os.environ.get('APP_USER_EMAIL')
    APP_USER_PASSWORD = os.environ.get('APP_USER_PASSWORD')

    # Caching and file settings
    CACHE_DIR = os.environ.get('CACHE_DIR', '.')  # change to instance path or shared storage for multi-instance
    AMAZON_CACHE_FILE = os.path.join(CACHE_DIR, os.environ.get('AMAZON_CACHE_FILE', 'amazon_cache.json'))
    AMAZON_ITEMS_CACHE_FILE = os.path.join(CACHE_DIR, os.environ.get('AMAZON_ITEMS_CACHE_FILE', 'amazon_items_cache.json'))
    RAPIDSHYP_CACHE_FILE = os.path.join(CACHE_DIR, os.environ.get('RAPIDSHYP_CACHE_FILE', 'rapidshyp_cache.json'))