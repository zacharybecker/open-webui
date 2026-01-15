"""
Confluence data source connector.

Syncs content from Atlassian Confluence spaces into Open WebUI knowledge bases.
"""

import logging
import re
from typing import Iterator, Optional

from open_webui.data_sources.base import (
    BaseDataSourceConnector,
    ConnectorRegistry,
    CredentialValidationResult,
    DocumentContent,
    SourceInfo,
    WebhookConfig,
)

log = logging.getLogger(__name__)

# HTML tag removal pattern
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_html_tags(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    if not html:
        return ""
    # Remove HTML tags
    text = HTML_TAG_PATTERN.sub(" ", html)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()


class ConfluenceConnector(BaseDataSourceConnector):
    """Connector for Atlassian Confluence."""

    source_type = "confluence"
    display_name = "Confluence"
    description = "Sync pages from Atlassian Confluence spaces"
    icon = "confluence"

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["space_key"],
            "properties": {
                "space_key": {
                    "type": "string",
                    "title": "Space Key",
                    "description": "The key of the Confluence space to sync",
                },
                "include_attachments": {
                    "type": "boolean",
                    "title": "Include Attachments",
                    "description": "Also sync text-based attachments",
                    "default": False,
                },
                "include_archived": {
                    "type": "boolean",
                    "title": "Include Archived Pages",
                    "description": "Include archived pages in sync",
                    "default": False,
                },
                "page_limit": {
                    "type": "integer",
                    "title": "Page Limit",
                    "description": "Maximum number of pages to sync (0 for unlimited)",
                    "default": 0,
                    "minimum": 0,
                },
            },
        }

    @classmethod
    def get_credentials_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["base_url", "username", "api_token"],
            "properties": {
                "base_url": {
                    "type": "string",
                    "title": "Confluence URL",
                    "description": "Your Confluence instance URL (e.g., https://yourcompany.atlassian.net/wiki)",
                    "format": "uri",
                },
                "username": {
                    "type": "string",
                    "title": "Username/Email",
                    "description": "Your Atlassian account email",
                },
                "api_token": {
                    "type": "string",
                    "title": "API Token",
                    "description": "API token from https://id.atlassian.com/manage-profile/security/api-tokens",
                    "format": "password",
                },
            },
        }

    def _get_client(self, credentials: dict):
        """Get Confluence API client."""
        try:
            from atlassian import Confluence
        except ImportError:
            raise ImportError(
                "atlassian-python-api is required for Confluence integration. "
                "Install it with: pip install atlassian-python-api"
            )

        return Confluence(
            url=credentials["base_url"],
            username=credentials["username"],
            password=credentials["api_token"],
            cloud=True,
        )

    def validate_credentials(self, credentials: dict) -> CredentialValidationResult:
        try:
            client = self._get_client(credentials)
            # Try to get current user info
            user = client.get_current_user()
            return CredentialValidationResult(
                valid=True,
                message="Successfully connected to Confluence",
                user_info={
                    "username": user.get("username", user.get("displayName")),
                    "email": user.get("email"),
                },
            )
        except ImportError as e:
            return CredentialValidationResult(valid=False, message=str(e))
        except Exception as e:
            log.exception(f"Confluence credential validation failed: {e}")
            return CredentialValidationResult(
                valid=False,
                message=f"Failed to connect: {str(e)}",
            )

    def list_available_sources(
        self, credentials: dict, search: Optional[str] = None
    ) -> list[SourceInfo]:
        try:
            client = self._get_client(credentials)
            spaces = client.get_all_spaces(limit=100, expand="description.plain")

            results = []
            for space in spaces.get("results", []):
                space_key = space.get("key", "")
                space_name = space.get("name", "")

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in space_key.lower()
                        and search_lower not in space_name.lower()
                    ):
                        continue

                description = ""
                if space.get("description", {}).get("plain", {}).get("value"):
                    description = space["description"]["plain"]["value"]

                results.append(
                    SourceInfo(
                        id=space_key,
                        name=space_name,
                        description=description,
                        url=f"{credentials['base_url']}/spaces/{space_key}",
                        metadata={"type": space.get("type", "global")},
                    )
                )

            return results
        except Exception as e:
            log.exception(f"Failed to list Confluence spaces: {e}")
            return []

    def fetch_content(
        self,
        config: dict,
        credentials: dict,
        last_sync_at: Optional[int] = None,
    ) -> Iterator[DocumentContent]:
        try:
            client = self._get_client(credentials)
            space_key = config["space_key"]
            page_limit = config.get("page_limit", 0)
            include_archived = config.get("include_archived", False)

            # Build CQL query
            cql = f'space="{space_key}" AND type=page'
            if not include_archived:
                cql += ' AND status="current"'

            # Get pages with content
            start = 0
            limit = 50
            pages_fetched = 0

            while True:
                results = client.cql(
                    cql,
                    start=start,
                    limit=limit,
                    expand="body.storage,version,history.lastUpdated",
                )

                page_results = results.get("results", [])
                if not page_results:
                    break

                for page in page_results:
                    try:
                        content_obj = page.get("content", page)
                        page_id = content_obj.get("id", "")
                        title = content_obj.get("title", "Untitled")

                        # Get page content
                        body = content_obj.get("body", {})
                        storage = body.get("storage", {})
                        html_content = storage.get("value", "")

                        # Convert HTML to plain text
                        text_content = strip_html_tags(html_content)

                        if not text_content:
                            continue

                        # Get last updated timestamp
                        history = content_obj.get("history", {})
                        last_updated = history.get("lastUpdated", {})
                        updated_when = last_updated.get("when")

                        # Build page URL
                        page_url = f"{credentials['base_url']}/pages/{page_id}"
                        links = content_obj.get("_links", {})
                        if links.get("webui"):
                            page_url = f"{credentials['base_url']}{links['webui']}"

                        yield DocumentContent(
                            external_id=f"confluence-{page_id}",
                            title=title,
                            content=text_content,
                            url=page_url,
                            content_type="text/plain",
                            metadata={
                                "space_key": space_key,
                                "page_id": page_id,
                                "source": "confluence",
                                "version": content_obj.get("version", {}).get(
                                    "number", 1
                                ),
                            },
                        )

                        pages_fetched += 1
                        if page_limit > 0 and pages_fetched >= page_limit:
                            return

                    except Exception as e:
                        log.error(f"Error processing Confluence page: {e}")
                        continue

                start += limit
                if len(page_results) < limit:
                    break

        except ImportError as e:
            log.error(str(e))
            raise
        except Exception as e:
            log.exception(f"Error fetching Confluence content: {e}")
            raise

    @classmethod
    def supports_webhooks(cls) -> bool:
        return True

    @classmethod
    def get_webhook_config(cls) -> WebhookConfig:
        return WebhookConfig(
            supported=True,
            url_path="/api/v1/data_sources/webhook/confluence",
            events=["page_created", "page_updated", "page_removed"],
            setup_instructions=(
                "To enable real-time sync, configure a webhook in Confluence:\n"
                "1. Go to Space Settings > Webhooks\n"
                "2. Add a new webhook with the URL provided\n"
                "3. Select the events: page_created, page_updated, page_removed"
            ),
        )


# Register the connector
ConnectorRegistry.register(ConfluenceConnector)
