"""
Jira data source connector.

Syncs issues from Atlassian Jira projects into Open WebUI knowledge bases.
"""

import logging
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


class JiraConnector(BaseDataSourceConnector):
    """Connector for Atlassian Jira."""

    source_type = "jira"
    display_name = "Jira"
    description = "Sync issues from Atlassian Jira projects"
    icon = "jira"

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["project_key"],
            "properties": {
                "project_key": {
                    "type": "string",
                    "title": "Project Key",
                    "description": "The key of the Jira project to sync (e.g., PROJ)",
                },
                "jql_filter": {
                    "type": "string",
                    "title": "JQL Filter",
                    "description": "Additional JQL filter to apply (e.g., 'status != Done')",
                    "default": "",
                },
                "include_comments": {
                    "type": "boolean",
                    "title": "Include Comments",
                    "description": "Include issue comments in the synced content",
                    "default": True,
                },
                "include_attachments": {
                    "type": "boolean",
                    "title": "Include Attachment Names",
                    "description": "Include attachment information in metadata",
                    "default": False,
                },
                "issue_limit": {
                    "type": "integer",
                    "title": "Issue Limit",
                    "description": "Maximum number of issues to sync (0 for unlimited)",
                    "default": 0,
                    "minimum": 0,
                },
                "issue_types": {
                    "type": "array",
                    "title": "Issue Types",
                    "description": "Only sync specific issue types (empty for all)",
                    "items": {"type": "string"},
                    "default": [],
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
                    "title": "Jira URL",
                    "description": "Your Jira instance URL (e.g., https://yourcompany.atlassian.net)",
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
        """Get Jira API client."""
        try:
            from atlassian import Jira
        except ImportError:
            raise ImportError(
                "atlassian-python-api is required for Jira integration. "
                "Install it with: pip install atlassian-python-api"
            )

        return Jira(
            url=credentials["base_url"],
            username=credentials["username"],
            password=credentials["api_token"],
            cloud=True,
        )

    def validate_credentials(self, credentials: dict) -> CredentialValidationResult:
        try:
            client = self._get_client(credentials)
            # Try to get current user info
            user = client.myself()
            return CredentialValidationResult(
                valid=True,
                message="Successfully connected to Jira",
                user_info={
                    "username": user.get("displayName", user.get("name")),
                    "email": user.get("emailAddress"),
                },
            )
        except ImportError as e:
            return CredentialValidationResult(valid=False, message=str(e))
        except Exception as e:
            log.exception(f"Jira credential validation failed: {e}")
            return CredentialValidationResult(
                valid=False,
                message=f"Failed to connect: {str(e)}",
            )

    def list_available_sources(
        self, credentials: dict, search: Optional[str] = None
    ) -> list[SourceInfo]:
        try:
            client = self._get_client(credentials)
            projects = client.projects()

            results = []
            for project in projects:
                project_key = project.get("key", "")
                project_name = project.get("name", "")

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in project_key.lower()
                        and search_lower not in project_name.lower()
                    ):
                        continue

                results.append(
                    SourceInfo(
                        id=project_key,
                        name=project_name,
                        description=project.get("description", ""),
                        url=f"{credentials['base_url']}/browse/{project_key}",
                        metadata={
                            "project_type": project.get("projectTypeKey", ""),
                            "style": project.get("style", ""),
                        },
                    )
                )

            return results
        except Exception as e:
            log.exception(f"Failed to list Jira projects: {e}")
            return []

    def _format_issue_content(
        self, issue: dict, include_comments: bool, credentials: dict
    ) -> str:
        """Format issue data into readable text content."""
        fields = issue.get("fields", {})
        lines = []

        # Issue key and summary
        key = issue.get("key", "")
        summary = fields.get("summary", "Untitled")
        lines.append(f"# {key}: {summary}")
        lines.append("")

        # Status and priority
        status = fields.get("status", {}).get("name", "Unknown")
        priority = fields.get("priority", {}).get("name", "None")
        issue_type = fields.get("issuetype", {}).get("name", "Issue")
        lines.append(f"**Type:** {issue_type}")
        lines.append(f"**Status:** {status}")
        lines.append(f"**Priority:** {priority}")
        lines.append("")

        # Assignee and reporter
        assignee = fields.get("assignee")
        if assignee:
            lines.append(f"**Assignee:** {assignee.get('displayName', 'Unassigned')}")
        reporter = fields.get("reporter")
        if reporter:
            lines.append(f"**Reporter:** {reporter.get('displayName', 'Unknown')}")
        lines.append("")

        # Description
        description = fields.get("description")
        if description:
            # Handle Atlassian Document Format (ADF)
            if isinstance(description, dict):
                description = self._parse_adf(description)
            lines.append("## Description")
            lines.append(description)
            lines.append("")

        # Labels
        labels = fields.get("labels", [])
        if labels:
            lines.append(f"**Labels:** {', '.join(labels)}")
            lines.append("")

        # Components
        components = fields.get("components", [])
        if components:
            component_names = [c.get("name", "") for c in components]
            lines.append(f"**Components:** {', '.join(component_names)}")
            lines.append("")

        # Comments
        if include_comments:
            comment_data = fields.get("comment", {})
            comments = comment_data.get("comments", [])
            if comments:
                lines.append("## Comments")
                lines.append("")
                for comment in comments[-10:]:  # Last 10 comments
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    body = comment.get("body", "")
                    if isinstance(body, dict):
                        body = self._parse_adf(body)
                    created = comment.get("created", "")[:10]
                    lines.append(f"**{author}** ({created}):")
                    lines.append(body)
                    lines.append("")

        return "\n".join(lines)

    def _parse_adf(self, adf: dict) -> str:
        """Parse Atlassian Document Format to plain text."""
        if not isinstance(adf, dict):
            return str(adf)

        content = adf.get("content", [])
        result = []

        for block in content:
            block_type = block.get("type", "")
            if block_type == "paragraph":
                text = self._extract_text_from_adf_block(block)
                result.append(text)
            elif block_type == "heading":
                text = self._extract_text_from_adf_block(block)
                level = block.get("attrs", {}).get("level", 1)
                result.append(f"{'#' * level} {text}")
            elif block_type == "bulletList":
                for item in block.get("content", []):
                    text = self._extract_text_from_adf_block(item)
                    result.append(f"- {text}")
            elif block_type == "orderedList":
                for i, item in enumerate(block.get("content", []), 1):
                    text = self._extract_text_from_adf_block(item)
                    result.append(f"{i}. {text}")
            elif block_type == "codeBlock":
                text = self._extract_text_from_adf_block(block)
                result.append(f"```\n{text}\n```")

        return "\n".join(result)

    def _extract_text_from_adf_block(self, block: dict) -> str:
        """Extract text from an ADF block."""
        content = block.get("content", [])
        texts = []
        for item in content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif item.get("content"):
                texts.append(self._extract_text_from_adf_block(item))
        return "".join(texts)

    def fetch_content(
        self,
        config: dict,
        credentials: dict,
        last_sync_at: Optional[int] = None,
    ) -> Iterator[DocumentContent]:
        try:
            client = self._get_client(credentials)
            project_key = config["project_key"]
            jql_filter = config.get("jql_filter", "")
            include_comments = config.get("include_comments", True)
            issue_limit = config.get("issue_limit", 0)
            issue_types = config.get("issue_types", [])

            # Build JQL query
            jql_parts = [f'project = "{project_key}"']

            if issue_types:
                types_str = ", ".join([f'"{t}"' for t in issue_types])
                jql_parts.append(f"issuetype IN ({types_str})")

            if jql_filter:
                jql_parts.append(f"({jql_filter})")

            jql = " AND ".join(jql_parts)
            jql += " ORDER BY updated DESC"

            # Fields to retrieve
            fields = [
                "summary",
                "description",
                "status",
                "priority",
                "assignee",
                "reporter",
                "labels",
                "components",
                "issuetype",
                "created",
                "updated",
            ]
            if include_comments:
                fields.append("comment")

            start = 0
            max_results = 50
            issues_fetched = 0

            while True:
                results = client.jql(
                    jql,
                    start=start,
                    limit=max_results,
                    fields=",".join(fields),
                )

                issues = results.get("issues", [])
                if not issues:
                    break

                for issue in issues:
                    try:
                        issue_key = issue.get("key", "")
                        fields_data = issue.get("fields", {})
                        summary = fields_data.get("summary", "Untitled")

                        # Format issue content
                        content = self._format_issue_content(
                            issue, include_comments, credentials
                        )

                        if not content:
                            continue

                        # Build issue URL
                        issue_url = f"{credentials['base_url']}/browse/{issue_key}"

                        yield DocumentContent(
                            external_id=f"jira-{issue_key}",
                            title=f"{issue_key}: {summary}",
                            content=content,
                            url=issue_url,
                            content_type="text/plain",
                            metadata={
                                "project_key": project_key,
                                "issue_key": issue_key,
                                "issue_type": fields_data.get("issuetype", {}).get(
                                    "name", ""
                                ),
                                "status": fields_data.get("status", {}).get("name", ""),
                                "source": "jira",
                            },
                        )

                        issues_fetched += 1
                        if issue_limit > 0 and issues_fetched >= issue_limit:
                            return

                    except Exception as e:
                        log.error(f"Error processing Jira issue: {e}")
                        continue

                start += max_results
                if len(issues) < max_results:
                    break

        except ImportError as e:
            log.error(str(e))
            raise
        except Exception as e:
            log.exception(f"Error fetching Jira content: {e}")
            raise

    @classmethod
    def supports_webhooks(cls) -> bool:
        return True

    @classmethod
    def get_webhook_config(cls) -> WebhookConfig:
        return WebhookConfig(
            supported=True,
            url_path="/api/v1/data_sources/webhook/jira",
            events=["jira:issue_created", "jira:issue_updated", "jira:issue_deleted"],
            setup_instructions=(
                "To enable real-time sync, configure a webhook in Jira:\n"
                "1. Go to Project Settings > Webhooks (or System Settings for global)\n"
                "2. Add a new webhook with the URL provided\n"
                "3. Select the events: Issue created, Issue updated, Issue deleted"
            ),
        )


# Register the connector
ConnectorRegistry.register(JiraConnector)
