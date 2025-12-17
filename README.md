# Zoho Pictures Sync

Sync images from Zoho Creator to Supabase Storage with automatic optimization.

## Features

- Incremental and full sync from Zoho Creator
- Automatic image optimization (WebP conversion, resize) for files > 5MB
- Organized storage by category and date
- Metadata preservation (tags, categories, Zoho record data)
- Simple web UI for monitoring and browsing
- Scheduled daily sync (configurable cron)

## Architecture

```
Zoho Creator → FastAPI (Railway) → Supabase Storage
                    ↓
              Supabase Postgres (metadata)
```

## Setup

### 1. Supabase Setup

1. Create a new Supabase project
2. Run the schema SQL in `backend/db/models.py` (SCHEMA_SQL constant) in the SQL editor
3. Create a storage bucket called `zoho-pictures` (or your preferred name)
4. Set bucket to private (signed URLs will be used)
5. Copy your project URL and service role key

### 2. Zoho OAuth Setup

1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a Self Client
3. Generate a refresh token with scopes:
   - `ZohoCreator.report.READ`
   - `ZohoCreator.form.READ`
4. Note your Client ID, Client Secret, and Refresh Token

### 3. Find Your Zoho App Details

- **Account Owner Name**: Your Zoho username (from URL when viewing app)
- **App Link Name**: The app's URL-safe name (from app URL)
- **Report Link Name**: The report's URL-safe name (from report URL)

Example: `https://creator.zoho.com/yourname/myapp/#Report:All_Records`
- Account Owner: `yourname`
- App Link Name: `myapp`
- Report Link Name: `All_Records`

### 4. Configure Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_REFRESH_TOKEN=your_refresh_token
ZOHO_ACCOUNT_OWNER_NAME=your_zoho_username
ZOHO_APP_LINK_NAME=your_app_name
ZOHO_REPORT_LINK_NAME=your_report_name

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=your_service_key
SUPABASE_STORAGE_BUCKET=zoho-pictures

SYNC_CRON=0 2 * * *
IMAGE_MAX_SIZE_MB=5
IMAGE_MAX_DIMENSION=4000
IMAGE_QUALITY=85
```

### 5. Customize Field Mapping

Edit `backend/main.py` in `get_sync_engine()` to match your Zoho form fields:

```python
_sync_engine = SyncEngine(
    # ...
    tag_fields=["Tags", "Project", "Location"],  # Fields to use as tags
    category_field="Category",                    # Field for folder organization
    description_field="Notes",                    # Field for image description
)
```

### 6. Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up

# Set environment variables
railway variables set ZOHO_CLIENT_ID=xxx
# ... set all variables
```

Or use the Railway dashboard to connect your repo and add variables.

### 7. Initial Sync

1. Open your Railway deployment URL
2. Click "Run Full Sync" to perform initial download
3. Monitor progress in the UI

## API Endpoints

- `GET /api/status` - Sync status and stats
- `POST /api/sync?full_sync=false` - Trigger sync
- `GET /api/images?tags=x&category=y` - List images
- `GET /api/runs` - List sync history
- `GET /api/health` - Health check

## Local Development

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with hot reload
uvicorn main:app --reload --port 8000
```

## Storage Organization

Images are stored in Supabase with paths like:
```
{category}/{YYYY-MM}/{zoho_record_id}_{field_name}.webp
```

Example: `Equipment/2024-01/12345_Photo.webp`

## Customization

### Image Processing

Adjust in `.env`:
- `IMAGE_MAX_SIZE_MB`: Threshold for optimization (default: 5)
- `IMAGE_MAX_DIMENSION`: Max pixel dimension (default: 4000)
- `IMAGE_QUALITY`: WebP quality 1-100 (default: 85)

### Sync Schedule

Default is 2 AM daily. Change `SYNC_CRON` using standard cron format:
- `0 2 * * *` = 2:00 AM daily
- `0 */6 * * *` = Every 6 hours
- `0 0 * * 0` = Weekly on Sunday

## Troubleshooting

**"Zoho token refresh failed"**
- Verify client ID/secret are correct
- Regenerate refresh token if expired

**"No images found in records"**
- Check that your report contains the image fields
- Verify field names match Zoho's internal names

**Images not appearing in UI**
- Check Supabase storage bucket exists
- Verify bucket name in env matches
