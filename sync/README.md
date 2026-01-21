# Simple Confluence to Open WebUI Knowledge Base Sync

This tool synchronizes a Confluence space to an Open WebUI knowledge base. It fetches pages from Confluence, converts them to text files, uploads them to Open WebUI for processing, and adds them to a knowledge base.

## Features

- **Incremental Sync**: Only processes changed or new pages on subsequent runs
- **Content Change Detection**: Uses SHA256 hashing to detect page modifications
- **Duplicate Prevention**: Avoids re-uploading unchanged content
- **Tracking File**: Maintains sync state in JSON file for efficiency
- Fetches all pages from a Confluence space
- Converts Confluence pages to clean text format
- Uploads files to Open WebUI with processing
- Waits for file processing to complete before adding to knowledge base
- Simple logging for progress tracking
- Minimal dependencies

## Prerequisites

1. **Open WebUI instance** running and accessible
2. **Confluence API access** with a user account and API token
3. **Python 3.7+** or Docker

## Dependencies

- requests
- atlassian-python-api

## Setup

### 1. Get Confluence API Token

1. Go to your Atlassian Account settings
2. Create an API token at: https://id.atlassian.com/manage-profile/security/api-tokens
3. Note down your email and the generated token

### 2. Get Open WebUI API Key

1. Log into your Open WebUI instance
2. Go to Settings → Account → API Keys
3. Generate a new API key

## Usage

### Command Line Arguments

**List available spaces:**
```bash
python confluence_sync.py --list-spaces \
                         --confluence-url https://your-company.atlassian.net \
                         --confluence-username your-email@company.com \
                         --confluence-token your-token
```

**Sync a single space:**
```bash
python confluence_sync.py --space-key YOUR_SPACE \
                         --openwebui-url http://localhost:3000 \
                         --api-key YOUR_API_KEY \
                         --confluence-url https://your-company.atlassian.net \
                         --confluence-username your-email@company.com \
                         --confluence-token your-token
```

**Sync multiple spaces:**
```bash
python confluence_sync.py --spaces "SPACE1,SPACE2,SPACE3" \
                         --openwebui-url http://localhost:3000 \
                         --api-key YOUR_API_KEY \
                         --confluence-url https://your-company.atlassian.net \
                         --confluence-username your-email@company.com \
                         --confluence-token your-token
```

**Sync all accessible spaces:**
```bash
python confluence_sync.py --sync-all-spaces \
                         --openwebui-url http://localhost:3000 \
                         --api-key YOUR_API_KEY \
                         --confluence-url https://your-company.atlassian.net \
                         --confluence-username your-email@company.com \
                         --confluence-token your-token
```

### Required Arguments

**For listing spaces:**
- `--confluence-url`: Confluence base URL
- `--confluence-username`: Confluence username/email
- `--confluence-token`: Confluence API token

**For syncing:**
- One of: `--space-key`, `--spaces`, or `--sync-all-spaces`
- `--openwebui-url`: Open WebUI base URL
- `--api-key`: Open WebUI API key
- `--confluence-url`: Confluence base URL
- `--confluence-username`: Confluence username/email
- `--confluence-token`: Confluence API token

### Optional Arguments

- `--knowledge-base-name`: Name for the knowledge base (default: Confluence-{space-key})
- `--description`: Knowledge base description
- `--force-recreate`: Delete and recreate the knowledge base if it exists
- `--force-refresh`: Force re-sync all pages, ignoring change detection
- `--tracking-file`: File to store sync tracking data (default: confluence_sync_tracking.json)
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

### Space Selection Options

- `--list-spaces`: List all accessible Confluence spaces and exit
- `--space-key`: Sync a single Confluence space
- `--spaces`: Sync multiple spaces (comma-separated: "SPACE1,SPACE2,SPACE3")
- `--sync-all-spaces`: Sync all spaces accessible to the user

## Docker Usage

```bash
# Build the image
docker build -t confluence-sync .

# Run the sync
docker run --rm confluence-sync \
  --space-key YOUR_SPACE \
  --openwebui-url http://localhost:3000 \
  --api-key YOUR_API_KEY \
  --confluence-url https://your-company.atlassian.net \
  --confluence-username your-email@company.com \
  --confluence-token your-token
```

## How It Works

### Space Discovery

**List all accessible spaces:**
```bash
python confluence_sync.py --list-spaces --confluence-url https://your-company.atlassian.net --confluence-username user@company.com --confluence-token token123
```

This will show a table of all spaces you can access (based on your Confluence permissions):
```
Available Confluence spaces:
--------------------------------------------------------------------------------
Space Key      Name                           Type
--------------------------------------------------------------------------------
DOCS           Documentation                  global
PROJ           Project Documentation         global
TEAM           Team Wiki                     global
```

**Note:** Only spaces you have permission to view in Confluence will be listed.

### Sync Process

1. **Authentication**: Connects to both Confluence and Open WebUI APIs
2. **Space Selection**: Gets pages from specified space(s) or all accessible spaces
3. **Incremental Check**: On subsequent runs, compares content hashes to detect changes
4. **Fetch Pages**: Retrieves all pages from the specified Confluence space(s)
5. **Content Extraction**: Downloads page content and converts HTML to clean text
6. **File Upload**: Uploads only new or changed pages as text files to Open WebUI
7. **Processing Wait**: Waits for Open WebUI to finish processing each file (embedding generation)
8. **Knowledge Base Integration**: Adds successfully processed files to the knowledge base
9. **Tracking Update**: Updates local tracking file with sync state for future runs

### Multiple Spaces

When syncing multiple spaces, each space gets its own knowledge base and tracking file:
- **Single space**: `confluence_sync_tracking.json`
- **Multiple spaces**: `confluence_sync_DOCS.json`, `confluence_sync_PROJ.json`, etc.

### Docker Usage

**List spaces:**
```bash
LIST_SPACES=true docker-compose -f sync/docker-compose.yml up
```

**Sync all spaces:**
```bash
SYNC_ALL_SPACES=true docker-compose -f sync/docker-compose.yml up
```

**Sync specific spaces:**
```bash
SPACES=DOCS,PROJ docker-compose -f sync/docker-compose.yml up
```

## Incremental Sync

The script maintains a tracking file (`confluence_sync_tracking.json`) that stores:

- Confluence page IDs and their corresponding Open WebUI file IDs
- Content hashes (SHA256) to detect changes
- Last modified timestamps from Confluence
- Sync timestamps

**Benefits:**
- **Faster subsequent runs**: Only processes changed pages
- **No duplicates**: Avoids re-uploading identical content
- **Change detection**: Automatically syncs when Confluence pages are modified
- **Cleanup**: Removes tracking for deleted Confluence pages

**Control Options:**
- `--force-refresh`: Re-sync all pages regardless of changes
- `--tracking-file`: Specify custom tracking file location

## Subsequent Runs

On the first run, the script will:
- Download all pages from Confluence
- Process and upload each page to Open WebUI
- Create a tracking file to remember sync state

On subsequent runs, the script will:
- Check which pages have changed (using SHA256 content hashes)
- Only process new or modified pages
- Skip unchanged pages (much faster!)
- Clean up tracking for pages deleted from Confluence

**Example Output:**
```
2024-01-20 10:00:00 - INFO - Found 50 pages in space MYSPACE
2024-01-20 10:00:01 - INFO - Checking 50 pages for changes...
2024-01-20 10:00:05 - INFO - Sync completed. Processed: 3, Skipped: 47, Removed: 0, Total: 50
```

This means only 3 pages changed since the last sync, and 47 were skipped for efficiency.

## Logging

The script provides detailed logging. Use `--log-level DEBUG` for verbose output:

```bash
python confluence_sync.py --log-level DEBUG [other arguments]
```

## Security Notes

- API keys are sent in HTTP headers - ensure HTTPS is used in production
- Store API keys securely, never commit them to version control
- The script requires write access to create temporary files

## Troubleshooting

### Common Issues

1. **Confluence API Access**:
   - Verify your API token is valid and not expired
   - Check that your user has access to the Confluence space

2. **Open WebUI Access**:
   - Ensure Open WebUI is running and accessible
   - Verify your API key is correct
   - Check that your user has permission to create knowledge bases

3. **File Processing Timeouts**:
   - Large files may take longer to process
   - The script waits up to 5 minutes per file
   - Check Open WebUI logs if files fail to process

4. **Network Issues**:
   - Ensure both services are accessible from where the script runs
   - Check firewall settings and proxy configurations