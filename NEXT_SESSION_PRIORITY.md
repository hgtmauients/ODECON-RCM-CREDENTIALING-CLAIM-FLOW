# Next Session Priority: Tenant-Configurable Settings via UI

## What to Build

Move all integration API keys and credentials from environment variables to per-tenant database storage, configurable through the Settings UI.

## Architecture

```
Settings Page (frontend)
    |
    | PUT /api/tenants/{tenant_id}/settings
    | GET /api/tenants/{tenant_id}/settings (sensitive values masked)
    |
    v
Tenant.settings JSONB column (already exists on tenants table)
    |
    | Sensitive values encrypted via services/encryption.py before storage
    |
    v
Services read config from DB first, fallback to env var
```

## Settings Categories to Move to DB

### Per-Tenant (each tenant configures their own)
- `api_cert_key` - License verification API key
- `caqh_org_id`, `caqh_username`, `caqh_password` - CAQH ProView credentials
- `smtp_host`, `smtp_port`, `smtp_user`, `smtp_pass`, `from_email` - Email settings
- `webhook_secret` - Webhook HMAC secret for this tenant

### System-Level (remain as env vars, not tenant-configurable)
- `DATABASE_URL` - DB connection
- `JWT_SECRET` / `JWT_JWKS_URL` / `JWT_ALGORITHM` - Auth config
- `CLAIMFLOW_ENCRYPTION_KEY` - Master encryption key
- `EDI_STORAGE_PATH` / `STORAGE_BACKEND` / `S3_BUCKET` - File storage
- `CORS_ORIGINS` - CORS config
- `ENV` - Environment mode

## Implementation Steps

### 1. Backend: Settings API endpoint
File: `backend/api/tenants.py`

Add:
- `PUT /api/tenants/{tenant_id}/settings` - Save settings (encrypt sensitive fields before storing in JSONB)
- `GET /api/tenants/{tenant_id}/settings` - Return settings with sensitive fields masked (show "***" + last 4 chars)

The `Tenant.settings` JSONB column already exists. Store as:
```json
{
  "api_cert_key_encrypted": "base64...",
  "caqh_org_id": "12345",
  "caqh_username": "user",
  "caqh_password_encrypted": "base64...",
  "smtp_host": "smtp.sendgrid.net",
  "smtp_port": 587,
  "smtp_user": "apikey",
  "smtp_pass_encrypted": "base64...",
  "from_email": "billing@practice.com",
  "webhook_secret_encrypted": "base64..."
}
```

### 2. Backend: Config resolver utility
File: `backend/core/tenant_config.py` (new)

```python
async def get_tenant_setting(db, tenant_id, key, default=None):
    """Get a setting from tenant DB, fallback to env var."""
    tenant = await get_tenant(db, tenant_id)
    if tenant and tenant.settings:
        value = tenant.settings.get(key)
        if value:
            # If it's an encrypted field, decrypt it
            if key.endswith('_encrypted'):
                return await decrypt_credential(value)
            return value
    # Fallback to environment variable
    return os.getenv(key.upper(), default)
```

### 3. Backend: Update services to use tenant config
Files to modify:
- `services/api_cert.py` - Read `api_cert_key` from tenant settings
- `services/caqh_proview.py` - Read CAQH credentials from tenant settings
- `services/email_service.py` - Read SMTP settings from tenant settings
- `api/credentialing.py` - Read webhook secret from tenant settings

Each service method needs `tenant_id` passed in (most already have it) and should call `get_tenant_setting()` instead of `os.getenv()`.

### 4. Frontend: Settings page with editable fields
File: `webapp/src/pages/admin/Settings.tsx` (rewrite)

Replace the current read-only env var display with:
- **Editable input fields** for each tenant-configurable setting
- **Save button** that calls `PUT /api/tenants/{id}/settings`
- **Sensitive fields** show as password inputs with show/hide
- **Test buttons** for SMTP (send test email), API-Cert (check usage), CAQH (test connection)
- **System info section** (read-only) showing backend status, DB connectivity

### 5. Database: No schema change needed
The `Tenant.settings` JSONB column already exists and can store arbitrary JSON.

## Files Changed
- `backend/api/tenants.py` - Add settings GET/PUT endpoints
- `backend/core/tenant_config.py` - New config resolver
- `backend/services/api_cert.py` - Use tenant config
- `backend/services/caqh_proview.py` - Use tenant config
- `backend/services/email_service.py` - Use tenant config
- `backend/api/credentialing.py` - Use tenant config for webhook secret
- `webapp/src/pages/admin/Settings.tsx` - Rewrite with editable fields

## Testing
- Verify settings save and load correctly
- Verify sensitive fields are encrypted in DB
- Verify masked display on GET
- Verify services read from DB when available, fall back to env var
- Verify each tenant can have different API keys
