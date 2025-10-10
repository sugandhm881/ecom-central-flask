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

    # --- CORRECTED AMAZON KEYS ---
    AWS_ACCESS_KEY = os.environ.get('AWS_MYACCESS_KEY') # Corrected
    AWS_SECRET_KEY = os.environ.get('AWS_MYSECRET_KEY') # Corrected
    AWS_REGION = os.environ.get('AWS_MYREGION')         # Corrected
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