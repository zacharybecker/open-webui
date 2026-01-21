#!/usr/bin/env python3
"""
Simple Confluence Space Sync Script for Open WebUI Knowledge Bases

This script synchronizes a Confluence space to an Open WebUI knowledge base.
It fetches pages from Confluence, converts them to text files, uploads them to Open WebUI,
waits for processing, and adds them to a knowledge base.

Usage:
    python confluence_sync.py --space-key YOUR_SPACE --openwebui-url http://localhost:3000 --api-key YOUR_API_KEY

Requirements:
    - requests
    - atlassian-python-api
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from atlassian import Confluence


class OpenWebUIClient:
    """Client for interacting with Open WebUI API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request to the Open WebUI API."""
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        if response.status_code >= 400:
            logging.error(f"API request failed: {method} {url} - {response.status_code}: {response.text}")
            response.raise_for_status()
        return response

    def get_knowledge_bases(self) -> List[Dict]:
        """Get all knowledge bases."""
        return self._request('GET', '/api/v1/knowledge/').json()['items']

    def create_knowledge_base(self, name: str, description: str = "") -> Dict:
        """Create a new knowledge base."""
        data = {"name": name, "description": description}
        return self._request('POST', '/api/v1/knowledge/create', json=data).json()

    def get_or_create_knowledge_base(self, name: str, description: str = "") -> Dict:
        """Get existing knowledge base or create new one."""
        for kb in self.get_knowledge_bases():
            if kb['name'] == name:
                logging.info(f"Found existing knowledge base: {name}")
                return kb

        logging.info(f"Creating new knowledge base: {name}")
        return self.create_knowledge_base(name, description)

    def upload_file(self, file_path: Path, filename: str = None) -> Dict:
        """Upload a file to Open WebUI."""
        filename = filename or file_path.name
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'text/plain')}
            return self._request('POST', '/api/v1/files/', files=files).json()

    def wait_for_file_processing(self, file_id: str, timeout: int = 300) -> bool:
        """Wait for file processing to complete."""
        start_time = time.time()
        logging.info(f"Waiting for file {file_id[:8]} processing...")

        while time.time() - start_time < timeout:
            try:
                status_data = self._request('GET', f'/api/v1/files/{file_id}/process/status').json()
                status = status_data.get('status')

                if status == 'completed':
                    logging.info(f"File {file_id[:8]} processing completed")
                    return True
                elif status == 'failed':
                    error = status_data.get('error', 'Unknown error')
                    logging.error(f"File {file_id[:8]} processing failed: {error}")
                    return False

                time.sleep(5)

            except Exception as e:
                logging.warning(f"Error checking file status: {e}")
                time.sleep(5)

        logging.error(f"File {file_id[:8]} processing timeout after {timeout}s")
        return False

    def add_file_to_knowledge_base(self, knowledge_base_id: str, file_id: str) -> Dict:
        """Add a file to a knowledge base."""
        data = {"file_id": file_id}
        return self._request('POST', f'/api/v1/knowledge/{knowledge_base_id}/file/add', json=data).json()


class ConfluenceClient:
    """Client for interacting with Confluence API."""

    def __init__(self, url: str, username: str, api_token: str):
        self.confluence = Confluence(url=url, username=username, password=api_token)

    def get_all_spaces(self) -> List[Dict]:
        """Get all spaces accessible to the user."""
        try:
            return self.confluence.get_all_spaces().get('results', [])
        except Exception as e:
            logging.error(f"Error fetching spaces: {e}")
            return []

    def get_space_pages(self, space_key: str, limit: int = 1000) -> List[Dict]:
        """Get all pages from a Confluence space."""
        pages = []
        start = 0

        while len(pages) < limit:
            try:
                result = self.confluence.get_all_pages_from_space(
                    space_key, start=start, limit=min(limit - len(pages), 100),
                    expand='body.storage,version'
                )
                if not result or len(result) < 100:
                    pages.extend(result)
                    break

                pages.extend(result)
                start += len(result)

            except Exception as e:
                logging.error(f"Error fetching pages: {e}")
                break

        return pages

    def get_page_content(self, page_id: str) -> tuple[str, str]:
        """Get the content of a Confluence page."""
        try:
            page = self.confluence.get_page_by_id(page_id, expand='body.storage,version')
            title = page['title']
            content = self._clean_html(page['body']['storage']['value'])
            return title, content
        except Exception as e:
            logging.error(f"Error getting page content for {page_id}: {e}")
            return "", ""

    @staticmethod
    def _clean_html(html_content: str) -> str:
        """Clean HTML content to plain text."""
        import re
        from html import unescape

        # Remove HTML tags, decode entities, and clean whitespace
        return re.sub(r'[ \t]+', ' ',
            re.sub(r'\n\s*\n', '\n\n',
            unescape(re.sub(r'<[^>]+>', '',
            unescape(html_content))))).strip()


class ConfluenceSync:
    """Main class for synchronizing Confluence space to Open WebUI."""

    def __init__(self, confluence_client: ConfluenceClient, openwebui_client: OpenWebUIClient, tracking_file: str = None):
        self.confluence = confluence_client
        self.openwebui = openwebui_client
        self.tracking_file = tracking_file or "confluence_sync_tracking.json"
        self.tracking_data = self._load_tracking()

    def _load_tracking(self) -> Dict:
        """Load tracking data from file."""
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Could not load tracking data: {e}")
        return {}

    def _save_tracking(self):
        """Save tracking data to file."""
        try:
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracking_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Could not save tracking data: {e}")

    @staticmethod
    def _content_hash(content: str) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _page_changed(self, page_id: str, content_hash: str, last_modified: str) -> bool:
        """Check if a page has changed since last sync."""
        if page_id not in self.tracking_data:
            return True

        tracked = self.tracking_data[page_id]
        return (tracked.get('content_hash') != content_hash or
                tracked.get('last_modified') != last_modified)

    def _update_tracking(self, page_id: str, file_id: str, content_hash: str, last_modified: str, title: str):
        """Update tracking data for a page."""
        self.tracking_data[page_id] = {
            'file_id': file_id,
            'content_hash': content_hash,
            'last_modified': last_modified,
            'title': title,
            'last_sync': time.time()
        }
        self._save_tracking()

    def sync_space(self, space_key: str, knowledge_base_name: str = None,
                   description: str = "", force_recreate: bool = False, force_refresh: bool = False) -> None:
        """Sync a Confluence space to a knowledge base."""

        kb_name = knowledge_base_name or f"Confluence-{space_key}"
        knowledge_base = self.openwebui.get_or_create_knowledge_base(kb_name, description)

        # Get Confluence pages
        logging.info(f"Fetching pages from Confluence space: {space_key}")
        pages = self.confluence.get_space_pages(space_key)

        if not pages:
            logging.warning(f"No pages found in space {space_key}")
            return

        logging.info(f"Found {len(pages)} pages in space {space_key}")
        logging.info(f"Checking {len(pages)} pages for changes...")

        # Process each page
        successful_uploads = 0
        skipped_pages = 0

        for i, page in enumerate(pages, 1):
            try:
                page_id = page['id']
                title = page.get('title', f'Page-{page_id}')
                last_modified = page.get('version', {}).get('when', '')

                # Get page content
                title, content = self.confluence.get_page_content(page_id)
                if not content:
                    logging.warning(f"Skipping page {page_id} - no content")
                    continue

                # Check if page has changed
                content_hash = self._content_hash(content)
                if not force_refresh and not self._page_changed(page_id, content_hash, last_modified):
                    skipped_pages += 1
                    logging.debug(f"Skipping unchanged page: {title}")
                    continue

                logging.info(f"Processing page {i}/{len(pages)}: {title}")

                # Create and upload temp file
                temp_file = self._create_temp_file(title, content)
                if not temp_file:
                    continue

                try:
                    # Upload and process file
                    upload_result = self.openwebui.upload_file(temp_file, f"{title}.txt")
                    file_id = upload_result['id']

                    logging.info(f"Uploaded file {file_id[:8]} for page: {title}")

                    if self.openwebui.wait_for_file_processing(file_id):
                        self.openwebui.add_file_to_knowledge_base(knowledge_base['id'], file_id)
                        self._update_tracking(page_id, file_id, content_hash, last_modified, title)
                        successful_uploads += 1
                        logging.info(f"Successfully synced page to knowledge base: {title}")

                finally:
                    temp_file.unlink(missing_ok=True)

            except Exception as e:
                logging.error(f"Error processing page {page.get('title', page_id)}: {e}")

        # Clean up removed pages from tracking
        current_page_ids = {page['id'] for page in pages}
        removed_pages = [pid for pid in self.tracking_data if pid not in current_page_ids]

        for pid in removed_pages:
            del self.tracking_data[pid]

        if removed_pages:
            self._save_tracking()
            logging.info(f"Cleaned up tracking for {len(removed_pages)} pages removed from Confluence")

        logging.info(f"Sync completed. Processed: {successful_uploads}, Skipped: {skipped_pages}, Removed: {len(removed_pages)}, Total: {len(pages)}")

    def _create_temp_file(self, title: str, content: str) -> Optional[Path]:
        """Create a temporary file with page content."""
        try:
            import re
            import tempfile

            # Sanitize filename
            safe_title = re.sub(r'[^\w\-_\. ]', '_', title).strip() or "untitled"

            # Create temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.txt', prefix='confluence_')
            temp_file = Path(temp_path)

            # Write content
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n{content}")

            return temp_file

        except Exception as e:
            logging.error(f"Error creating temp file for {title}: {e}")
            return None


def list_spaces(confluence_client: ConfluenceClient):
    """List all available Confluence spaces."""
    spaces = confluence_client.get_all_spaces()
    if not spaces:
        logging.error("No spaces found or access denied")
        return

    print("Available Confluence spaces:")
    print("-" * 80)
    print(f"{'Key':<15} {'Name':<40} {'Type':<10} {'Status'}")
    print("-" * 80)
    for space in spaces:
        print(f"{space.get('key',''):<15} {space.get('name',''):<40} {space.get('type',''):<10} {space.get('status','')}")


def get_spaces_to_sync(args, confluence_client: ConfluenceClient) -> list[str]:
    """Determine which spaces to sync based on arguments."""
    if args.sync_all_spaces:
        spaces = [s['key'] for s in confluence_client.get_all_spaces()]
        logging.info(f"Syncing all {len(spaces)} accessible spaces")
        return spaces
    elif args.spaces:
        spaces = [s.strip() for s in args.spaces.split(',')]
        logging.info(f"Syncing {len(spaces)} specified spaces: {', '.join(spaces)}")
        return spaces
    elif args.space_key:
        return [args.space_key]
    else:
        logging.error("Specify --space-key, --spaces, or --sync-all-spaces to sync")
        return []


def main():
    parser = argparse.ArgumentParser(description="Sync Confluence space to Open WebUI knowledge base")
    parser.add_argument('--space-key', help='Confluence space key (use --list-spaces to see available spaces)')
    parser.add_argument('--spaces', help='Comma-separated list of space keys to sync')
    parser.add_argument('--sync-all-spaces', action='store_true', help='Sync all accessible spaces')
    parser.add_argument('--list-spaces', action='store_true', help='List all accessible Confluence spaces and exit')
    parser.add_argument('--openwebui-url', help='Open WebUI base URL (required for sync)')
    parser.add_argument('--api-key', help='Open WebUI API key (required for sync)')
    parser.add_argument('--confluence-url', required=True, help='Confluence base URL')
    parser.add_argument('--confluence-username', required=True, help='Confluence username')
    parser.add_argument('--confluence-token', required=True, help='Confluence API token')
    parser.add_argument('--knowledge-base-name', help='Name for the knowledge base (default: Confluence-{space-key})')
    parser.add_argument('--description', default='', help='Knowledge base description')
    parser.add_argument('--force-recreate', action='store_true', help='Force recreation of knowledge base')
    parser.add_argument('--force-refresh', action='store_true', help='Force re-sync all pages, ignoring change detection')
    parser.add_argument('--tracking-file', default='confluence_sync_tracking.json', help='File to store sync tracking data')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        confluence_client = ConfluenceClient(args.confluence_url, args.confluence_username, args.confluence_token)

        if args.list_spaces:
            list_spaces(confluence_client)
            return

        spaces_to_sync = get_spaces_to_sync(args, confluence_client)
        if not spaces_to_sync:
            return

        if not args.openwebui_url or not args.api_key:
            logging.error("--openwebui-url and --api-key are required for sync")
            return

        openwebui_client = OpenWebUIClient(args.openwebui_url, args.api_key)

        for space_key in spaces_to_sync:
            try:
                tracking_file = f"confluence_sync_{space_key}.json" if len(spaces_to_sync) > 1 else args.tracking_file
                sync = ConfluenceSync(confluence_client, openwebui_client, tracking_file)

                logging.info(f"Starting sync for space: {space_key}")
                sync.sync_space(space_key, args.knowledge_base_name, args.description,
                               args.force_recreate, args.force_refresh)
                logging.info(f"Completed sync for space: {space_key}")

            except Exception as e:
                logging.error(f"Failed to sync space {space_key}: {e}")

        logging.info("All space syncs completed")

    except Exception as e:
        logging.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()