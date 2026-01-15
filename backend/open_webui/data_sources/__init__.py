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

__all__ = [
    "BaseDataSourceConnector",
    "DocumentContent",
    "ConnectorRegistry",
    "get_connector",
    "get_available_source_types",
]
