"""
Base class and utilities for external data source connectors.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional

from pydantic import BaseModel

log = logging.getLogger(__name__)


@dataclass
class DocumentContent:
    """Represents a document fetched from an external source."""

    external_id: str  # Unique ID in the external system
    title: str
    content: str  # Text content of the document
    url: Optional[str] = None  # Link to the original document
    content_type: str = "text/plain"
    metadata: dict = field(default_factory=dict)  # Additional metadata
    updated_at: Optional[int] = None  # Unix timestamp of last update


class SourceInfo(BaseModel):
    """Information about an available source (space, project, repo, etc.)."""

    id: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[dict] = None


class CredentialValidationResult(BaseModel):
    """Result of credential validation."""

    valid: bool
    message: Optional[str] = None
    user_info: Optional[dict] = None  # Info about the authenticated user


class WebhookConfig(BaseModel):
    """Configuration for webhook-based sync."""

    supported: bool = False
    url_path: str = ""
    events: list[str] = []
    setup_instructions: Optional[str] = None


class BaseDataSourceConnector(ABC):
    """
    Abstract base class for external data source connectors.
    
    Each connector implementation handles communication with a specific
    external service (Confluence, Jira, GitHub, etc.).
    """

    # Class attributes to be overridden by subclasses
    source_type: str = ""
    display_name: str = ""
    description: str = ""
    icon: str = ""  # Icon identifier or SVG

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> dict:
        """
        Return JSON schema for the connector's configuration.
        
        This defines what configuration options are available
        (e.g., space key, project ID, repository name).
        """
        pass

    @classmethod
    @abstractmethod
    def get_credentials_schema(cls) -> dict:
        """
        Return JSON schema for the connector's credentials.
        
        This defines what credentials are needed
        (e.g., API token, username, OAuth tokens).
        """
        pass

    @abstractmethod
    def validate_credentials(self, credentials: dict) -> CredentialValidationResult:
        """
        Validate the provided credentials.
        
        Args:
            credentials: Dictionary of credential values
            
        Returns:
            CredentialValidationResult with validation status
        """
        pass

    @abstractmethod
    def list_available_sources(
        self, credentials: dict, search: Optional[str] = None
    ) -> list[SourceInfo]:
        """
        List available sources (spaces, projects, repos) the credentials have access to.
        
        Args:
            credentials: Validated credentials
            search: Optional search filter
            
        Returns:
            List of available sources
        """
        pass

    @abstractmethod
    def fetch_content(
        self,
        config: dict,
        credentials: dict,
        last_sync_at: Optional[int] = None,
    ) -> Iterator[DocumentContent]:
        """
        Fetch content from the external source.
        
        Args:
            config: Source configuration (which space/project/repo to sync)
            credentials: Authentication credentials
            last_sync_at: Unix timestamp of last sync (for incremental sync)
            
        Yields:
            DocumentContent objects for each document
        """
        pass

    @classmethod
    def supports_webhooks(cls) -> bool:
        """Return whether this connector supports webhook-based sync."""
        return False

    @classmethod
    def get_webhook_config(cls) -> WebhookConfig:
        """Return webhook configuration for this connector."""
        return WebhookConfig(supported=False)

    def handle_webhook(
        self,
        payload: dict,
        headers: dict,
        config: dict,
        credentials: dict,
    ) -> Iterator[DocumentContent]:
        """
        Handle an incoming webhook notification.
        
        Args:
            payload: Webhook payload
            headers: Request headers
            config: Source configuration
            credentials: Authentication credentials
            
        Yields:
            DocumentContent objects for updated documents
        """
        raise NotImplementedError("Webhook handling not implemented")

    @classmethod
    def get_type_info(cls) -> dict:
        """Return complete type information for this connector."""
        return {
            "id": cls.source_type,
            "name": cls.display_name,
            "description": cls.description,
            "icon": cls.icon,
            "config_schema": cls.get_config_schema(),
            "credentials_schema": cls.get_credentials_schema(),
            "supports_webhooks": cls.supports_webhooks(),
        }


class ConnectorRegistry:
    """Registry for data source connectors."""

    _connectors: dict[str, type[BaseDataSourceConnector]] = {}

    @classmethod
    def register(cls, connector_class: type[BaseDataSourceConnector]) -> None:
        """Register a connector class."""
        if not connector_class.source_type:
            raise ValueError(f"Connector {connector_class} has no source_type defined")
        cls._connectors[connector_class.source_type] = connector_class
        log.info(f"Registered data source connector: {connector_class.source_type}")

    @classmethod
    def get(cls, source_type: str) -> Optional[type[BaseDataSourceConnector]]:
        """Get a connector class by source type."""
        return cls._connectors.get(source_type)

    @classmethod
    def get_all(cls) -> dict[str, type[BaseDataSourceConnector]]:
        """Get all registered connectors."""
        return cls._connectors.copy()

    @classmethod
    def get_available_types(cls) -> list[dict]:
        """Get type information for all registered connectors."""
        return [
            connector.get_type_info() for connector in cls._connectors.values()
        ]


def get_connector(source_type: str) -> Optional[BaseDataSourceConnector]:
    """
    Get an instance of a connector by source type.
    
    Args:
        source_type: The type of connector (e.g., "confluence", "jira")
        
    Returns:
        Connector instance, or None if not found
    """
    connector_class = ConnectorRegistry.get(source_type)
    if connector_class:
        return connector_class()
    return None


def get_available_source_types() -> list[dict]:
    """Get information about all available source types."""
    return ConnectorRegistry.get_available_types()
