# Membership-Enabled Bokeh App - Deployment Guide

## 📦 Files You Have

1. **main_with_membership.py** - Complete Bokeh app with membership tiers
2. **ghost_auth.py** - Ghost authentication module
3. **main_optimized.py** - Original version without membership (backup)

## 🚀 Quick Start (3 Steps)

### Step 1: Setup Environment

```bash
# Install required package
pip install pyjwt

# Set environment variable
export GHOST_URL="https://eastasiaecon.com"
# Or add to .env file:
echo "GHOST_URL=https://eastasiaecon.com" >> .env
```

### Step 2: Copy Files

```bash
# In your app directory
cp main_with_membership.py app/main.py
cp ghost_auth.py app/ghost_auth.py
```

### Step 3: Test Locally

```bash
# Test with full access (dev mode - no ghost_auth.py)
bokeh serve app --show

# Test with membership system
# (Make sure ghost_auth.py is present)
bokeh serve app --show
```

## 🎯 Access Levels Summary

| Tier | Can View | Can Interact | Countries | Products | Animate | Download |
|------|----------|--------------|-----------|----------|---------|----------|
| **Public** | ✅ | ❌ | View only | View only | ❌ | ❌ |
| **Members** | ✅ | ✅ Limited | Top 10 | Limited | ❌ | ❌ |
| **Daily** | ✅ | ✅ | Top 20 | All | ✅ | ✅ |
| **Daily+Data** | ✅ | ✅ | Unlimited | All | ✅ | ✅ |
| **East Asia** | ✅ | ✅ | Unlimited | All | ✅ | ✅ |

### Detailed Restrictions:

#### Public Users
- Can see the charts and data
- Cannot change any selections (all dropdowns disabled)
- Cannot use the month slider
- Cannot animate
- Cannot download
- See signup prompt

#### Members
- Can interact with controls
- Limited to: Autos, Parts, EVs, Total products
- Can only select top 10 countries
- Cannot animate (Play button disabled)
- Cannot download
- See upgrade prompt to Daily

#### Daily Subscribers  
- Full product selection
- Can select top 20 countries
- Can animate
- Can download CSV files
- See upgrade prompt to Daily+Data for unlimited countries

#### Daily+Data & East Asia (Premium)
- Complete unlimited access
- All countries
- All products
- All features
- No upgrade prompts

## 🔧 Configuration

### Environment Variables

Create `.env` file in your app directory:

```bash
# Required
GHOST_URL=https://eastasiaecon.com

# Optional (for production with actual Ghost JWT verification)
GHOST_ADMIN_API_KEY=your_admin_api_key_here
```

### Customizing Tier Access

Edit `ghost_auth.py` to modify tier permissions:

```python
TIER_CONFIG = {
    'members': {
        'can_view': True,
        'can_interact': True,
        'can_download': False,
        'can_change_selections': True,
        'can_animate': False,
        'max_countries': 10,  # Change this number
        'limited_products': True,
    },
    # ... other tiers
}
```

### Customizing Limited Products

Edit `main_with_membership.py` around line 250:

```python
if member_manager.has_limited_products():
    # Change these to your desired limited set
    allowed_products = {'Autos', 'Parts', 'EVs', 'Total'}
    products = products & allowed_products
```

## 🌐 Ghost Integration

### Option 1: Embed in Ghost (Recommended)

Create a members-only page/post in Ghost:

```html
<!-- In Ghost editor, HTML card -->
<iframe 
    src="https://your-domain.com/bokeh-app" 
    width="100%" 
    height="1400px" 
    frameborder="0"
    style="border: none;">
</iframe>

<script>
// Pass Ghost session to iframe
window.addEventListener('message', function(e) {
    if (e.data.type === 'ghost-session') {
        // Session is automatically passed via cookies
    }
});
</script>
```

### Option 2: Standalone with Ghost Auth

Deploy Bokeh app separately and configure nginx to pass cookies:

```nginx
location /bokeh-app/ {
    proxy_pass http://localhost:5006/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    
    # CRITICAL: Pass cookies for authentication
    proxy_set_header Cookie $http_cookie;
    
    # WebSocket support for Bokeh
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Timeouts
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
}
```

## 🧪 Testing Different Tiers

### Test Public Access

1. Open app in incognito/private window
2. Should see "Public (View Only)" badge
3. All controls should be disabled
4. Signup prompt should be visible

### Test Members Access

1. Login to Ghost as a basic member
2. Should see "Member" badge
3. Can interact but with limited countries/products
4. No animate or download buttons

### Test Premium Access

1. Login as Daily+Data or East Asia member
2. Should see "Premium Subscriber" badge
3. All features enabled
4. No upgrade prompts

## 🔍 Debugging

### Check Authentication

Add this to your app to see auth status:

```python
print(f"[DEBUG] Tier: {member_manager.tier}")
print(f"[DEBUG] Can interact: {member_manager.can_interact()}")
print(f"[DEBUG] Can download: {member_manager.can_download()}")
print(f"[DEBUG] Max countries: {member_manager.get_max_countries()}")
```

### Check Ghost Cookies

In browser console:

```javascript
console.log(document.cookie);
// Should see: ghost-members-ssr=...
```

### Fallback Mode

If `ghost_auth.py` is not found or errors, the app automatically runs in "Dev Mode" with full access enabled. This is perfect for local development.

## 📊 Analytics

Track tier usage by adding to your code:

```python
# In main_with_membership.py, after tier detection
import logging
logging.info(f"User session: tier={member_manager.tier}")
```

## 🚨 Troubleshooting

### "Module not found: ghost_auth"
- Make sure `ghost_auth.py` is in the same directory as `main.py`
- Check file permissions: `chmod 644 ghost_auth.py`

### Cookies not passing through
- Check nginx config includes `proxy_set_header Cookie`
- Verify Ghost and Bokeh app are on same domain
- Check browser isn't blocking third-party cookies

### All users showing as "Public"
- Verify Ghost session cookie exists
- Check JWT decoding (might need Ghost content API key)
- Test with a simple print statement of cookies

### Wrong tier detected
- Check Ghost member tier names match exactly
- Tier names are case-sensitive
- Verify member has active subscription

## 🔐 Security Notes

1. **JWT Verification**: For production, implement full JWT signature verification with Ghost's content API key
2. **Rate Limiting**: Add rate limiting to prevent abuse
3. **Session Validation**: Periodically revalidate Ghost sessions
4. **HTTPS Only**: Always use HTTPS in production
5. **CORS**: Configure appropriate CORS headers

## 📈 Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY ghost_auth.py ./app/

ENV GHOST_URL=https://eastasiaecon.com
EXPOSE 5006

CMD ["bokeh", "serve", "app", "--address", "0.0.0.0", "--port", "5006", "--allow-websocket-origin=*"]
```

### Requirements.txt

```
bokeh>=3.0.0
pandas>=1.5.0
numpy>=1.23.0
pyarrow>=10.0.0
geopandas>=0.12.0  # optional
pyjwt>=2.8.0
python-dotenv>=1.0.0  # optional, for .env support
```

## ✅ Launch Checklist

- [ ] Set GHOST_URL environment variable
- [ ] Copy main_with_membership.py to app/main.py
- [ ] Copy ghost_auth.py to app/
- [ ] Install pyjwt: `pip install pyjwt`
- [ ] Test locally without ghost_auth.py (dev mode)
- [ ] Test locally with ghost_auth.py
- [ ] Configure nginx to pass cookies
- [ ] Deploy to production
- [ ] Test all tier levels in production
- [ ] Monitor logs for authentication issues
- [ ] Set up analytics/monitoring

## 🎉 You're Ready!

Your app now has full membership integration with Ghost! Users will automatically see the appropriate features based on their subscription tier.

For questions or issues, check the logs for `[AUTH]` prefixed messages.
