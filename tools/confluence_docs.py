"""
title: Confluence Documentation
description: Search and retrieve documentation from Atlassian Confluence. Supports both Cloud and Data Center/Server deployments.
author: Open WebUI
version: 0.1.0
requirements: markdownify, aiohttp
"""

import json
import re
import base64
import logging
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# =============================================================================
# Module-level helpers (not exposed to the model)
# =============================================================================


def _validate_config(valves) -> Optional[str]:
    """Check required Valves fields are set. Returns error JSON string or None."""
    if not valves.confluence_base_url:
        return json.dumps(
            {"error": "Confluence base URL is not configured. An admin must set it in the tool's Valves settings."}
        )
    if valves.auth_type == "cloud":
        if not valves.email or not valves.api_token:
            return json.dumps(
                {"error": "Cloud auth requires both email and API token. An admin must configure them in Valves."}
            )
    elif valves.auth_type == "datacenter":
        if not valves.api_token:
            return json.dumps(
                {"error": "Data Center auth requires a Personal Access Token. An admin must configure it in Valves."}
            )
    else:
        return json.dumps(
            {"error": f"Unknown auth_type '{valves.auth_type}'. Must be 'cloud' or 'datacenter'."}
        )
    return None


def _get_auth_headers(valves) -> dict:
    """Build authentication headers based on auth_type."""
    if valves.auth_type == "cloud":
        credentials = base64.b64encode(
            f"{valves.email}:{valves.api_token}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }
    else:
        return {
            "Authorization": f"Bearer {valves.api_token}",
            "Content-Type": "application/json",
        }


async def _make_confluence_request(
    valves, endpoint: str, params: Optional[dict] = None
) -> dict:
    """Make an async GET request to the Confluence REST API.

    Returns a dict with either the parsed JSON response or an 'error' key.
    """
    base = valves.confluence_base_url.rstrip("/")
    url = f"{base}{endpoint}"
    headers = _get_auth_headers(valves)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                ssl=valves.verify_ssl,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:
                    return {"error": "Authentication failed. Check your credentials in Valves."}
                elif resp.status == 403:
                    return {"error": "Permission denied. The configured account lacks access to this resource."}
                elif resp.status == 404:
                    return {"error": "Resource not found. Check that the URL and resource ID are correct."}
                elif resp.status == 429:
                    return {"error": "Rate limited by Confluence. Try again in a moment."}
                else:
                    body = await resp.text()
                    return {"error": f"Confluence returned HTTP {resp.status}: {body[:500]}"}
    except aiohttp.ClientConnectorError as e:
        return {"error": f"Cannot connect to Confluence at {base}. Check the URL. Details: {e}"}
    except asyncio.TimeoutError:
        return {"error": "Request to Confluence timed out after 30 seconds."}
    except Exception as e:
        log.exception(f"Confluence request error: {e}")
        return {"error": f"Unexpected error contacting Confluence: {e}"}


def _html_to_markdown(html: str, max_length: int) -> str:
    """Convert Confluence storage-format HTML to Markdown.

    Strips Confluence-specific ac:* and ri:* XML tags, converts to Markdown
    via markdownify, collapses excessive whitespace, and truncates.
    """
    from markdownify import markdownify as md

    # Strip Confluence-specific XML tags (ac:structured-macro, ri:attachment, etc.)
    cleaned = re.sub(r"</?(?:ac|ri):[^>]*>", "", html)

    # Convert HTML to Markdown
    text = md(cleaned, heading_style="ATX", strip=["script", "style"])

    # Collapse runs of 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse runs of 3+ spaces into 1
    text = re.sub(r" {3,}", " ", text)

    text = text.strip()

    if len(text) > max_length:
        text = text[:max_length] + "\n\n[Content truncated...]"

    return text


def _parse_space_metadata(json_str: str) -> dict:
    """Safely parse the space_metadata JSON string. Returns {} on failure."""
    if not json_str or not json_str.strip():
        return {}
    try:
        result = json.loads(json_str)
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


# Need asyncio for the TimeoutError reference in _make_confluence_request
import asyncio


# =============================================================================
# Tools class
# =============================================================================


class Tools:
    class Valves(BaseModel):
        confluence_base_url: str = Field(
            default="",
            description="Confluence instance URL (e.g. https://yoursite.atlassian.net)",
        )
        auth_type: str = Field(
            default="cloud",
            description="Authentication type: 'cloud' (email + API token) or 'datacenter' (Personal Access Token)",
        )
        email: str = Field(
            default="",
            description="Email address for Confluence Cloud authentication (ignored for datacenter)",
        )
        api_token: str = Field(
            default="",
            description="API token (Cloud) or Personal Access Token (Data Center)",
        )
        space_metadata: str = Field(
            default="{}",
            description='JSON map of space keys to custom descriptions, e.g. {"ENG": "Engineering docs", "HR": "HR policies"}',
        )
        max_results: int = Field(
            default=10,
            description="Default maximum number of results per query",
        )
        verify_ssl: bool = Field(
            default=True,
            description="Verify SSL certificates when connecting to Confluence",
        )
        max_page_length: int = Field(
            default=20000,
            description="Maximum characters before page content is truncated",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def list_spaces(self) -> str:
        """
        List all available Confluence spaces with their keys, names, and descriptions.
        Use this to discover what documentation spaces exist before searching.

        :return: JSON list of spaces with key, name, and description
        """
        error = _validate_config(self.valves)
        if error:
            return error

        data = await _make_confluence_request(
            self.valves,
            "/rest/api/space",
            params={
                "expand": "description.plain",
                "limit": str(self.valves.max_results),
            },
        )

        if "error" in data:
            return json.dumps(data)

        metadata = _parse_space_metadata(self.valves.space_metadata)
        spaces = []

        for space in data.get("results", []):
            key = space.get("key", "")
            name = space.get("name", "")

            # Build description: admin metadata first, then Confluence native
            description_parts = []
            if key in metadata:
                description_parts.append(metadata[key])

            confluence_desc = (
                space.get("description", {})
                .get("plain", {})
                .get("value", "")
                .strip()
            )
            if confluence_desc:
                description_parts.append(confluence_desc)

            spaces.append(
                {
                    "key": key,
                    "name": name,
                    "description": " | ".join(description_parts) if description_parts else "",
                }
            )

        return json.dumps(spaces, ensure_ascii=False)

    async def search_confluence(self, query: str, space_key: str = None) -> str:
        """
        Search Confluence pages by text. Optionally scope the search to a specific space.
        Use list_spaces first to discover available space keys.

        :param query: The text to search for across page content and titles
        :param space_key: Optional space key to limit search to a single space (e.g. "ENG")
        :return: JSON list of matching pages with id, title, space, and excerpt
        """
        error = _validate_config(self.valves)
        if error:
            return error

        # Escape double quotes in the query to prevent CQL injection
        safe_query = query.replace('"', '\\"')

        cql = f'type=page AND text~"{safe_query}"'
        if space_key:
            safe_space = space_key.replace('"', '\\"')
            cql = f'space="{safe_space}" AND {cql}'

        data = await _make_confluence_request(
            self.valves,
            "/rest/api/content/search",
            params={
                "cql": cql,
                "expand": "space,version",
                "limit": str(self.valves.max_results),
            },
        )

        if "error" in data:
            return json.dumps(data)

        results = []
        for page in data.get("results", []):
            results.append(
                {
                    "id": page.get("id", ""),
                    "title": page.get("title", ""),
                    "space": {
                        "key": page.get("space", {}).get("key", ""),
                        "name": page.get("space", {}).get("name", ""),
                    },
                    "last_modified": page.get("version", {}).get("when", ""),
                    "excerpt": page.get("excerpt", ""),
                }
            )

        return json.dumps(results, ensure_ascii=False)

    async def get_page_content(self, page_id: str) -> str:
        """
        Get the full content of a Confluence page by its ID.
        Use search_confluence first to find page IDs.

        :param page_id: The numeric ID of the Confluence page to retrieve
        :return: JSON with page title, space, metadata, and Markdown-formatted content
        """
        error = _validate_config(self.valves)
        if error:
            return error

        data = await _make_confluence_request(
            self.valves,
            f"/rest/api/content/{page_id}",
            params={"expand": "body.storage,space,version"},
        )

        if "error" in data:
            return json.dumps(data)

        html_body = data.get("body", {}).get("storage", {}).get("value", "")
        markdown_content = _html_to_markdown(html_body, self.valves.max_page_length)

        return json.dumps(
            {
                "id": data.get("id", ""),
                "title": data.get("title", ""),
                "space": {
                    "key": data.get("space", {}).get("key", ""),
                    "name": data.get("space", {}).get("name", ""),
                },
                "version": data.get("version", {}).get("number", ""),
                "last_modified": data.get("version", {}).get("when", ""),
                "modified_by": data.get("version", {}).get("by", {}).get("displayName", ""),
                "content": markdown_content,
            },
            ensure_ascii=False,
        )

    async def get_space_pages(self, space_key: str, limit: int = 25) -> str:
        """
        List pages in a Confluence space for browsing. Returns page IDs, titles,
        and last modified dates. Use this to explore what pages exist in a space.

        :param space_key: The space key to list pages from (e.g. "ENG")
        :param limit: Maximum number of pages to return (default: 25)
        :return: JSON list of pages with id, title, and last_modified date
        """
        error = _validate_config(self.valves)
        if error:
            return error

        data = await _make_confluence_request(
            self.valves,
            f"/rest/api/space/{space_key}/content/page",
            params={
                "expand": "version",
                "limit": str(limit),
            },
        )

        if "error" in data:
            return json.dumps(data)

        pages = []
        for page in data.get("page", {}).get("results", data.get("results", [])):
            pages.append(
                {
                    "id": page.get("id", ""),
                    "title": page.get("title", ""),
                    "last_modified": page.get("version", {}).get("when", ""),
                }
            )

        return json.dumps(pages, ensure_ascii=False)
