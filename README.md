# Zoho Pictures Sync

Sync images from Zoho Creator to Supabase Storage with automatic optimization and a modern React UI.

## Features

- **Modern React UI** with shadcn/ui components
- **Virtualized gallery** supporting 100k+ images
- **Smart filtering** by Job Captain Timesheet, Project, Department
- **Lightbox viewer** with zoom, pan, rotate, keyboard navigation
- **Bulk download** as ZIP
- **Admin settings panel** for configuration via UI
- **Incremental/full sync** from Zoho Creator
- **Automatic image optimization** (WebP conversion, resize)
- **Scheduled daily sync** (configurable cron)

## Architecture

```
Zoho Creator → FastAPI (Railway) → Supabase Storage
                    ↓
              Supabase Postgres (metadata)
                    ↓
              React Frontend (bundled)
```

## Quick Start

### 1. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Run this SQL in the SQL Editor:

```sql
CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zoho_record_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    original_filename TEXT,
    storage_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    was_processed BOOLEAN DEFAULT FALSE,
    tags TEXT[],
    category TEXT,
    description TEXT,
    job_captain_timesheet TEXT,
    project_name TEXT,
    department TEXT,
    zoho_metadata JSONB,
    zoho_created_at TIMESTAMP,
    zoho_modified_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(zoho_record_id, field_name)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running',
    records_processed INTEGER DEFAULT 0,
    images_synced INTEGER DEFAULT 0,
    images_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_log JSONB
);

CREATE INDEX IF NOT EXISTS idx_images_job_captain ON images(job_captain_timesheet);
CREATE INDEX IF NOT EXISTS idx_images_project ON images(project_name);
CREATE INDEX IF NOT EXISTS idx_images_department ON images(department);
CREATE INDEX IF NOT EXISTS idx_images_synced_at ON images(synced_at DESC);
```

3. Create storage bucket: `zoho-pictures` (private)

### 2. Zoho OAuth Setup

1. Go to [api-console.zoho.com](https://api-console.zoho.com)
2. Create a **Self Client**
3. Generate refresh token with scopes:
   - `ZohoCreator.report.READ`
   - `ZohoCreator.form.READ`

### 3. Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

Or manually:

```bash
railway login
railway init
railway up
```

### 4. Set Environment Variables

In Railway dashboard, add these variables:

| Variable | Description |
|----------|-------------|
| `ZOHO_CLIENT_ID` | OAuth client ID |
| `ZOHO_CLIENT_SECRET` | OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | OAuth refresh token |
| `ZOHO_ACCOUNT_OWNER_NAME` | Your Zoho username |
| `ZOHO_APP_LINK_NAME` | App URL name |
| `ZOHO_REPORT_LINK_NAME` | Report URL name |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service role key |
| `SUPABASE_STORAGE_BUCKET` | `zoho-pictures` |

### 5. Configure Field Mappings

Open your deployed app → **Settings** tab:

| Setting | Your Zoho Field |
|---------|-----------------|
| Job Captain Timesheet | `Add_Job_Captain_Time_Sheet_Number` |
| Project Name | `Project` |
| Department | `Project_Department` |

### 6. Run Initial Sync

1. Open **Dashboard**
2. Click **Full Sync**
3. Monitor progress

## Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Sync status and stats |
| `/api/sync` | POST | Trigger sync (`?full_sync=true`) |
| `/api/images` | GET | List images with filters |
| `/api/images/filters` | GET | Get filter dropdown values |
| `/api/config` | GET/PUT | Read/update configuration |
| `/api/config/test-zoho` | POST | Test Zoho connection |
| `/api/runs` | GET | Sync run history |
| `/api/health` | GET | Health check |

## Configuration

### Via UI (Settings Page)

- Zoho credentials and app details
- Field mappings for categorization
- Image processing settings
- Sync schedule

### Via Environment Variables

```env
SYNC_CRON=0 2 * * *        # 2 AM daily
IMAGE_MAX_SIZE_MB=5         # Optimize files > 5MB
IMAGE_MAX_DIMENSION=4000    # Max pixel dimension
IMAGE_QUALITY=85            # WebP quality (1-100)
```

## Troubleshooting

**"Zoho token refresh failed"**
- Verify credentials in Settings → Test Connection
- Regenerate refresh token if expired

**"No images found"**
- Check field mappings match Zoho field names exactly
- Verify report contains image fields

**Images not loading**
- Check Supabase storage bucket exists
- Verify bucket is set to private (signed URLs used)
