"""
GitHub data source connector.

Syncs content from GitHub repositories into Open WebUI knowledge bases.
"""

import base64
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

# File extensions to include by default
DEFAULT_INCLUDE_EXTENSIONS = [
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".bash",
    ".dockerfile",
]

# Files to exclude
EXCLUDE_PATTERNS = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "composer.lock",
    "Gemfile.lock",
    ".min.js",
    ".min.css",
    ".bundle.js",
]


class GitHubConnector(BaseDataSourceConnector):
    """Connector for GitHub repositories."""

    source_type = "github"
    display_name = "GitHub"
    description = "Sync files from GitHub repositories"
    icon = "github"

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["repository"],
            "properties": {
                "repository": {
                    "type": "string",
                    "title": "Repository",
                    "description": "Repository in owner/repo format (e.g., octocat/Hello-World)",
                },
                "branch": {
                    "type": "string",
                    "title": "Branch",
                    "description": "Branch to sync (leave empty for default branch)",
                    "default": "",
                },
                "path": {
                    "type": "string",
                    "title": "Path",
                    "description": "Subdirectory path to sync (leave empty for entire repo)",
                    "default": "",
                },
                "include_extensions": {
                    "type": "array",
                    "title": "File Extensions",
                    "description": "File extensions to include (empty for defaults)",
                    "items": {"type": "string"},
                    "default": [],
                },
                "include_readme": {
                    "type": "boolean",
                    "title": "Include README files",
                    "description": "Include README.md files",
                    "default": True,
                },
                "include_docs": {
                    "type": "boolean",
                    "title": "Include Documentation",
                    "description": "Include files from docs/ directory",
                    "default": True,
                },
                "include_code": {
                    "type": "boolean",
                    "title": "Include Source Code",
                    "description": "Include source code files",
                    "default": True,
                },
                "max_file_size_kb": {
                    "type": "integer",
                    "title": "Max File Size (KB)",
                    "description": "Maximum file size in KB to sync",
                    "default": 500,
                    "minimum": 1,
                    "maximum": 10000,
                },
                "file_limit": {
                    "type": "integer",
                    "title": "File Limit",
                    "description": "Maximum number of files to sync (0 for unlimited)",
                    "default": 0,
                    "minimum": 0,
                },
            },
        }

    @classmethod
    def get_credentials_schema(cls) -> dict:
        return {
            "type": "object",
            "required": ["access_token"],
            "properties": {
                "access_token": {
                    "type": "string",
                    "title": "Personal Access Token",
                    "description": "GitHub Personal Access Token with repo read access",
                    "format": "password",
                },
                "enterprise_url": {
                    "type": "string",
                    "title": "Enterprise URL",
                    "description": "GitHub Enterprise URL (leave empty for github.com)",
                    "format": "uri",
                    "default": "",
                },
            },
        }

    def _get_client(self, credentials: dict):
        """Get GitHub API client."""
        try:
            from github import Github, GithubException
            from github import Auth
        except ImportError:
            raise ImportError(
                "PyGithub is required for GitHub integration. "
                "Install it with: pip install PyGithub"
            )

        auth = Auth.Token(credentials["access_token"])
        
        enterprise_url = credentials.get("enterprise_url", "")
        if enterprise_url:
            return Github(base_url=f"{enterprise_url}/api/v3", auth=auth)
        return Github(auth=auth)

    def validate_credentials(self, credentials: dict) -> CredentialValidationResult:
        try:
            client = self._get_client(credentials)
            user = client.get_user()
            return CredentialValidationResult(
                valid=True,
                message="Successfully connected to GitHub",
                user_info={
                    "username": user.login,
                    "name": user.name,
                    "email": user.email,
                },
            )
        except ImportError as e:
            return CredentialValidationResult(valid=False, message=str(e))
        except Exception as e:
            log.exception(f"GitHub credential validation failed: {e}")
            return CredentialValidationResult(
                valid=False,
                message=f"Failed to connect: {str(e)}",
            )

    def list_available_sources(
        self, credentials: dict, search: Optional[str] = None
    ) -> list[SourceInfo]:
        try:
            client = self._get_client(credentials)
            user = client.get_user()

            results = []

            # Get user's repositories
            repos = user.get_repos(sort="updated", direction="desc")

            for repo in repos:
                if repo.archived:
                    continue

                full_name = repo.full_name
                name = repo.name

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in full_name.lower()
                        and search_lower not in (repo.description or "").lower()
                    ):
                        continue

                results.append(
                    SourceInfo(
                        id=full_name,
                        name=name,
                        description=repo.description or "",
                        url=repo.html_url,
                        metadata={
                            "private": repo.private,
                            "language": repo.language,
                            "stars": repo.stargazers_count,
                            "default_branch": repo.default_branch,
                        },
                    )
                )

                # Limit results
                if len(results) >= 100:
                    break

            return results
        except Exception as e:
            log.exception(f"Failed to list GitHub repositories: {e}")
            return []

    def _should_include_file(self, file_path: str, config: dict) -> bool:
        """Check if a file should be included based on config."""
        # Check exclude patterns
        for pattern in EXCLUDE_PATTERNS:
            if pattern in file_path:
                return False

        # Get filename and extension
        filename = file_path.split("/")[-1].lower()
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1]

        # Check README
        if filename in ["readme.md", "readme.txt", "readme.rst", "readme"]:
            return config.get("include_readme", True)

        # Check docs
        if "/docs/" in file_path.lower() or file_path.lower().startswith("docs/"):
            return config.get("include_docs", True)

        # Get allowed extensions
        include_extensions = config.get("include_extensions", [])
        if not include_extensions:
            include_extensions = DEFAULT_INCLUDE_EXTENSIONS

        # Check code files
        if ext in include_extensions:
            return config.get("include_code", True)

        return False

    def fetch_content(
        self,
        config: dict,
        credentials: dict,
        last_sync_at: Optional[int] = None,
    ) -> Iterator[DocumentContent]:
        try:
            client = self._get_client(credentials)
            repo_name = config["repository"]
            branch = config.get("branch", "")
            path = config.get("path", "")
            max_file_size_kb = config.get("max_file_size_kb", 500)
            file_limit = config.get("file_limit", 0)

            repo = client.get_repo(repo_name)

            # Use default branch if not specified
            if not branch:
                branch = repo.default_branch

            # Get repository contents
            files_fetched = 0

            def process_contents(contents):
                nonlocal files_fetched

                for content in contents:
                    if file_limit > 0 and files_fetched >= file_limit:
                        return

                    if content.type == "dir":
                        # Recursively process directories
                        try:
                            sub_contents = repo.get_contents(content.path, ref=branch)
                            yield from process_contents(sub_contents)
                        except Exception as e:
                            log.warning(f"Error accessing directory {content.path}: {e}")
                            continue
                    elif content.type == "file":
                        # Check if we should include this file
                        if not self._should_include_file(content.path, config):
                            continue

                        # Check file size
                        if content.size > max_file_size_kb * 1024:
                            log.debug(
                                f"Skipping {content.path}: exceeds max file size"
                            )
                            continue

                        try:
                            # Get file content
                            file_content = content.decoded_content.decode("utf-8")

                            if not file_content.strip():
                                continue

                            yield DocumentContent(
                                external_id=f"github-{repo_name}-{content.sha[:8]}",
                                title=content.path,
                                content=file_content,
                                url=content.html_url,
                                content_type="text/plain",
                                metadata={
                                    "repository": repo_name,
                                    "branch": branch,
                                    "path": content.path,
                                    "sha": content.sha,
                                    "size": content.size,
                                    "source": "github",
                                },
                            )

                            files_fetched += 1

                        except UnicodeDecodeError:
                            log.debug(f"Skipping binary file: {content.path}")
                            continue
                        except Exception as e:
                            log.warning(f"Error reading file {content.path}: {e}")
                            continue

            # Start fetching from the specified path
            try:
                initial_contents = repo.get_contents(path or "", ref=branch)
                if not isinstance(initial_contents, list):
                    initial_contents = [initial_contents]
                yield from process_contents(initial_contents)
            except Exception as e:
                log.exception(f"Error fetching repository contents: {e}")
                raise

        except ImportError as e:
            log.error(str(e))
            raise
        except Exception as e:
            log.exception(f"Error fetching GitHub content: {e}")
            raise

    @classmethod
    def supports_webhooks(cls) -> bool:
        return True

    @classmethod
    def get_webhook_config(cls) -> WebhookConfig:
        return WebhookConfig(
            supported=True,
            url_path="/api/v1/data_sources/webhook/github",
            events=["push", "create", "delete"],
            setup_instructions=(
                "To enable real-time sync, configure a webhook in GitHub:\n"
                "1. Go to repository Settings > Webhooks\n"
                "2. Add a new webhook with the URL provided\n"
                "3. Set Content type to application/json\n"
                "4. Select events: Push events"
            ),
        )


# Register the connector
ConnectorRegistry.register(GitHubConnector)
