# ghost_auth.py
# Ghost member authentication for Bokeh app

import os
import jwt
import requests
from functools import wraps
from typing import Optional, Dict

# Ghost configuration
GHOST_URL = os.getenv('GHOST_URL', 'https://your-ghost-site.com')
GHOST_ADMIN_API_KEY = os.getenv('GHOST_ADMIN_API_KEY', '')

# Member tiers configuration
TIER_CONFIG = {
    'public': {
        'can_view': True,
        'can_interact': False,
        'can_download': False,
        'can_change_selections': False,
        'can_animate': False,
        'max_countries': 0,
    },
    'members': {
        'can_view': True,
        'can_interact': True,
        'can_download': False,
        'can_change_selections': True,
        'can_animate': False,
        'max_countries': 10,  # Can only see top 10
        'limited_products': True,  # Only some products
    },
    'Daily': {
        'can_view': True,
        'can_interact': True,
        'can_download': True,
        'can_change_selections': True,
        'can_animate': True,
        'max_countries': 20,
        'limited_products': False,
    },
    'Daily+Data': {
        'can_view': True,
        'can_interact': True,
        'can_download': True,
        'can_change_selections': True,
        'can_animate': True,
        'max_countries': None,  # Unlimited
        'limited_products': False,
    },
    'East Asia': {
        'can_view': True,
        'can_interact': True,
        'can_download': True,
        'can_change_selections': True,
        'can_animate': True,
        'max_countries': None,  # Unlimited
        'limited_products': False,
    }
}

def get_member_tier_from_cookie(request) -> str:
    """
    Extract member tier from Ghost session cookie.
    Returns tier name or 'public' if not authenticated.
    """
    try:
        # Get the Ghost session cookie
        cookies = request.cookies
        ghost_session = cookies.get('ghost-members-ssr', None)
        
        if not ghost_session:
            return 'public'
        
        # Decode the JWT token (Ghost uses JWT for member sessions)
        # Note: You'll need the Ghost content API key to verify the signature
        decoded = jwt.decode(ghost_session, options={"verify_signature": False})
        
        # Get member tiers from the decoded token
        tiers = decoded.get('tiers', [])
        
        # Check for premium tiers first (priority order)
        tier_names = [tier.get('name', '').strip() for tier in tiers]
        
        # Return highest tier
        if 'Daily+Data' in tier_names or 'East Asia' in tier_names:
            return 'Daily+Data'  # Treat both as full access
        elif 'Daily' in tier_names:
            return 'Daily'
        elif len(tiers) > 0:
            return 'members'
        else:
            return 'public'
            
    except Exception as e:
        print(f"[AUTH] Error getting member tier: {e}")
        return 'public'

def get_permissions(tier: str) -> Dict:
    """Get permissions for a given tier."""
    return TIER_CONFIG.get(tier, TIER_CONFIG['public'])

def requires_tier(min_tier: str):
    """Decorator to check if user has required tier."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # This would be called in the Bokeh callback context
            # For now, we'll handle this at the app level
            return func(*args, **kwargs)
        return wrapper
    return decorator

class MembershipManager:
    """Manages member tier and permissions for the Bokeh session."""
    
    def __init__(self, tier: str = 'public'):
        self.tier = tier
        self.permissions = get_permissions(tier)
    
    def can_download(self) -> bool:
        return self.permissions['can_download']
    
    def can_animate(self) -> bool:
        return self.permissions['can_animate']
    
    def can_change_selections(self) -> bool:
        return self.permissions['can_change_selections']
    
    def can_interact(self) -> bool:
        return self.permissions['can_interact']
    
    def get_max_countries(self) -> Optional[int]:
        return self.permissions.get('max_countries')
    
    def has_limited_products(self) -> bool:
        return self.permissions.get('limited_products', False)
    
    def get_upgrade_message(self) -> str:
        """Get appropriate upgrade message based on current tier."""
        if self.tier == 'public':
            return "Sign up for a membership to interact with this data"
        elif self.tier == 'members':
            return "Upgrade to Daily tier for full functionality and downloads"
        elif self.tier == 'Daily':
            return "Upgrade to Daily+Data or East Asia tier for unlimited data access"
        return ""
    
    def get_tier_display_name(self) -> str:
        """Get display name for current tier."""
        tier_names = {
            'public': 'Public (View Only)',
            'members': 'Member',
            'Daily': 'Daily Subscriber',
            'Daily+Data': 'Premium Subscriber',
            'East Asia': 'Premium Subscriber'
        }
        return tier_names.get(self.tier, 'Unknown')
