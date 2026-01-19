"""
GitHub data source connector.

Syncs content from GitHub repositories into Open WebUI knowledge bases.
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

from github import GithubException

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

    def _normalize_enterprise_url(self, enterprise_url: str) -> str:
        """Normalize enterprise URL to base URL only."""
        if not enterprise_url:
            return ""
        
        original_url = enterprise_url
        
        # Remove trailing slashes
        enterprise_url = enterprise_url.rstrip("/")
        
        # Remove .git suffix if present
        if enterprise_url.endswith(".git"):
            enterprise_url = enterprise_url[:-4]
        
        # Extract base URL (remove any path components)
        # Handle both http:// and https://
        if "://" in enterprise_url:
            parts = enterprise_url.split("://", 1)
            scheme = parts[0]
            rest = parts[1]
            # Remove any path after the domain
            if "/" in rest:
                rest = rest.split("/")[0]
            enterprise_url = f"{scheme}://{rest}"
        
        # Log if we had to normalize
        if original_url != enterprise_url:
            log.debug(f"Normalized enterprise URL from '{original_url}' to '{enterprise_url}'")
        
        return enterprise_url

    def _get_api_base_url(self, credentials: dict) -> str:
        """Get the GitHub API base URL."""
        enterprise_url = credentials.get("enterprise_url", "")
        if enterprise_url:
            normalized = self._normalize_enterprise_url(enterprise_url)
            if normalized:
                # For regular GitHub.com, use the standard API endpoint
                if normalized in ("https://github.com", "http://github.com"):
                    return "https://api.github.com"
                # For GitHub Enterprise, use the enterprise API endpoint
                return f"{normalized}/api/v3"
        return "https://api.github.com"

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
            normalized = self._normalize_enterprise_url(enterprise_url)
            if normalized:
                return Github(base_url=f"{normalized}/api/v3", auth=auth)
        return Github(auth=auth)

    def validate_credentials(self, credentials: dict) -> CredentialValidationResult:
        try:
            try:
                import requests
            except ImportError:
                requests = None
            
            client = self._get_client(credentials)
            
            # Use direct API call to avoid PyGithub lazy loading issues
            api_base = self._get_api_base_url(credentials)
            
            token = credentials["access_token"]
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            
            # Make direct API call to /user endpoint
            user_info = {}
            if requests:
                try:
                    response = requests.get(f"{api_base}/user", headers=headers, timeout=10)
                    response.raise_for_status()
                    user_data = response.json()
                    
                    user_info = {
                        "username": user_data.get("login"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                    }
                except Exception as e:
                    log.warning(f"Direct API call failed, trying PyGithub fallback: {e}")
                    # Fallback to PyGithub approach
                    user = client.get_user()
                    try:
                        user_info["username"] = user.login
                    except (GithubException, AttributeError):
                        user_info["username"] = None
                    try:
                        user_info["name"] = user.name
                    except (GithubException, AttributeError):
                        user_info["name"] = None
                    try:
                        user_info["email"] = user.email
                    except (GithubException, AttributeError):
                        user_info["email"] = None
            else:
                # Fallback to PyGithub if requests not available
                user = client.get_user()
                try:
                    user_info["username"] = user.login
                except (GithubException, AttributeError):
                    user_info["username"] = None
                try:
                    user_info["name"] = user.name
                except (GithubException, AttributeError):
                    user_info["name"] = None
                try:
                    user_info["email"] = user.email
                except (GithubException, AttributeError):
                    user_info["email"] = None
            
            # If we got the user object, credentials are valid even if some properties are missing
            return CredentialValidationResult(
                valid=True,
                message="Successfully connected to GitHub",
                user_info=user_info,
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
            try:
                import requests
            except ImportError:
                requests = None
            
            client = self._get_client(credentials)
            
            # Use direct API calls if requests is available, otherwise fallback to PyGithub
            if requests:
                # Get username first using direct API call
                api_base = self._get_api_base_url(credentials)
                
                token = credentials["access_token"]
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                }
                
                # Get username via direct API call
                username = None
                try:
                    response = requests.get(f"{api_base}/user", headers=headers, timeout=10)
                    response.raise_for_status()
                    user_data = response.json()
                    username = user_data.get("login")
                except Exception as e:
                    log.warning(f"Could not get username via direct API: {e}")
                    # Fallback to PyGithub
                    try:
                        user = client.get_user()
                        username = user.login
                    except (GithubException, AttributeError):
                        pass
                
                if not username:
                    log.warning("Could not determine username")
                    return []

                results = []

                # Fetch repositories using direct API calls with pagination
                page = 1
                per_page = 100
                max_pages = 10  # Limit to prevent infinite loops
                
                while page <= max_pages:
                    try:
                        # Use direct API call to get repos
                        params = {
                            "sort": "updated",
                            "direction": "desc",
                            "per_page": per_page,
                            "page": page,
                        }
                        response = requests.get(
                            f"{api_base}/user/repos",
                            headers=headers,
                            params=params,
                            timeout=10,
                        )
                        
                        # Handle rate limiting
                        if response.status_code == 404:
                            log.warning(f"404 error fetching repositories (page {page})")
                            break
                        elif response.status_code == 403:
                            log.warning("403 Forbidden - token may lack repo scope")
                            break
                        
                        response.raise_for_status()
                        repos_data = response.json()
                        
                        # If no repos returned, we've reached the end
                        if not repos_data:
                            break
                        
                        # Process repositories
                        for repo_data in repos_data:
                            try:
                                # Skip archived repos
                                if repo_data.get("archived", False):
                                    continue
                                
                                full_name = repo_data.get("full_name", "")
                                name = repo_data.get("name", "")
                                
                                if not full_name or not name:
                                    continue
                                
                                # Apply search filter if provided
                                if search:
                                    description = repo_data.get("description", "") or ""
                                    search_lower = search.lower()
                                    if (
                                        search_lower not in full_name.lower()
                                        and search_lower not in description.lower()
                                    ):
                                        continue
                                
                                # Build metadata
                                metadata = {
                                    "private": repo_data.get("private", False),
                                    "language": repo_data.get("language"),
                                    "stars": repo_data.get("stargazers_count", 0),
                                    "default_branch": repo_data.get("default_branch", "main"),
                                }
                                
                                url = repo_data.get("html_url", f"https://github.com/{full_name}")
                                description = repo_data.get("description", "") or ""
                                
                                results.append(
                                    SourceInfo(
                                        id=full_name,
                                        name=name,
                                        description=description,
                                        url=url,
                                        metadata=metadata,
                                    )
                                )
                                
                                # Limit results
                                if len(results) >= 100:
                                    return results
                            except Exception as e:
                                log.warning(f"Error processing repository: {e}")
                                continue
                        
                        # Check if we got fewer repos than requested (last page)
                        if len(repos_data) < per_page:
                            break
                        
                        page += 1
                    except Exception as e:
                        log.warning(f"Error fetching repositories page {page}: {e}")
                        break
                
                return results
            else:
                # Fallback to PyGithub if requests not available
                try:
                    user = client.get_user()
                    username = None
                    try:
                        username = user.login
                    except (GithubException, AttributeError):
                        pass
                    
                    if not username:
                        log.warning("Could not determine username")
                        return []
                    
                    repos = user.get_repos(sort="updated", direction="desc")
                    results = []
                    
                    # Limit to first 100 repos to avoid pagination issues
                    for i, repo in enumerate(repos):
                        if i >= 100:
                            break
                        try:
                            if repo.archived:
                                continue
                            
                            full_name = repo.full_name
                            name = repo.name
                            
                            if search:
                                desc = repo.description or ""
                                if search.lower() not in full_name.lower() and search.lower() not in desc.lower():
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
                        except GithubException:
                            continue
                    
                    return results
                except GithubException as e:
                    log.warning(f"PyGithub fallback failed: {e}")
                    return []
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
