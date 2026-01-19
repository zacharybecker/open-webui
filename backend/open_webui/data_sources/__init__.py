"""
External Data Source Connectors for Knowledge Bases.

This module provides a pluggable architecture for syncing content from
external services (Confluence, Jira, GitHub, etc.) into Open WebUI knowledge bases.
"""

from open_webui.data_sources.base import (
    BaseDataSourceConnector,
    DocumentContent,
    ConnectorRegistry,
    get_connector,
    get_available_source_types,
)


def register_default_connectors() -> None:
    """Register built-in data source connectors."""
    from open_webui.data_sources import confluence, github, jira

    _ = (confluence, github, jira)

__all__ = [
    "BaseDataSourceConnector",
    "DocumentContent",
    "ConnectorRegistry",
    "get_connector",
    "get_available_source_types",
    "register_default_connectors",
]
