"""
Shared sync logic for external data sources.
"""

import logging
import time
import uuid
from typing import Optional

from fastapi import Request
from starlette.datastructures import Headers
from sqlalchemy.orm import Session

from open_webui.models.data_sources import DataSources, DataSourceSyncResult
from open_webui.models.knowledge import Knowledges
from open_webui.models.files import Files, FileForm, FileUpdateForm
from open_webui.routers.retrieval import process_file, ProcessFileForm
from open_webui.utils.crypto import decrypt_credentials
from open_webui.data_sources import get_connector

log = logging.getLogger(__name__)


def build_internal_request(app_state) -> Request:
    """Create a minimal Request with access to app.state."""

    class _AppWrapper:
        def __init__(self, state):
            self.state = state

    return Request(
        {
            "type": "http",
            "asgi.version": "3.0",
            "asgi.spec_version": "2.0",
            "method": "GET",
            "path": "/internal",
            "query_string": b"",
            "headers": Headers({}).raw,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 80),
            "scheme": "http",
            "app": _AppWrapper(app_state),
        }
    )


def _decrypt_data_source_credentials(data_source) -> Optional[dict]:
    """Decrypt credentials from a data source."""
    if not data_source.credentials:
        return None
    encrypted = data_source.credentials.get("encrypted")
    if not encrypted:
        return data_source.credentials
    return decrypt_credentials(encrypted)


def sync_data_source(
    request: Request,
    data_source_id: str,
    user,
    db: Session,
) -> DataSourceSyncResult:
    """Perform sync for a data source."""
    start_time = time.time()
    errors = []
    files_synced = 0
    files_updated = 0

    data_source = DataSources.get_data_source_by_id(data_source_id, db=db)
    if not data_source:
        return DataSourceSyncResult(
            success=False,
            errors=["Data source not found"],
        )

    # Update status to syncing
    DataSources.update_data_source_status(data_source_id, "syncing", db=db)

    try:
        # Get connector
        connector = get_connector(data_source.source_type)
        if not connector:
            raise ValueError(f"Unknown source type: {data_source.source_type}")

        # Decrypt credentials
        credentials = _decrypt_data_source_credentials(data_source)
        if not credentials:
            raise ValueError("Missing credentials")

        existing_files = Knowledges.get_files_by_id(data_source.knowledge_id, db=db)
        existing_by_external_id = {}
        for file in existing_files:
            meta = file.meta or {}
            if meta.get("data_source_id") != data_source_id:
                continue
            external_id = meta.get("external_id")
            if not external_id:
                continue
            if (
                external_id not in existing_by_external_id
                or file.updated_at > existing_by_external_id[external_id].updated_at
            ):
                existing_by_external_id[external_id] = file

        # Fetch content
        for doc in connector.fetch_content(
            config=data_source.config or {},
            credentials=credentials,
            last_sync_at=data_source.last_sync_at,
        ):
            try:
                existing_file = existing_by_external_id.get(doc.external_id)
                file_meta = {
                    "name": doc.title,
                    "content_type": doc.content_type,
                    "size": len(doc.content),
                    "external_id": doc.external_id,
                    "external_url": doc.url,
                    "data_source_id": data_source_id,
                    "source": data_source.source_type,
                    **doc.metadata,
                }

                if existing_file:
                    existing_data = existing_file.data or {}
                    existing_meta = existing_file.meta or {}
                    content_changed = existing_data.get("content") != doc.content
                    meta_changed = any(
                        existing_meta.get(key) != value
                        for key, value in file_meta.items()
                    )

                    if content_changed or meta_changed:
                        Files.update_file_by_id(
                            existing_file.id,
                            FileUpdateForm(
                                data={"content": doc.content} if content_changed else None,
                                meta=file_meta if meta_changed else None,
                            ),
                            db=db,
                        )

                        if content_changed:
                            try:
                                process_file(
                                    request,
                                    ProcessFileForm(
                                        file_id=existing_file.id,
                                        collection_name=data_source.knowledge_id,
                                    ),
                                    user=user,
                                    db=db,
                                )
                            except Exception as e:
                                log.warning(
                                    f"Failed to process updated file {doc.title}: {e}"
                                )
                            files_updated += 1
                    continue

                # Create a file from the document content
                file_id = str(uuid.uuid4())

                # Create file record
                file_form = FileForm(
                    id=file_id,
                    filename=f"{doc.title}.txt",
                    path="",
                    data={"content": doc.content},
                    meta=file_meta,
                )

                file = Files.insert_new_file(user.id, file_form, db=db)
                if not file:
                    errors.append(f"Failed to create file for {doc.title}")
                    continue

                # Process file for vector DB
                try:
                    process_file(
                        request,
                        ProcessFileForm(
                            file_id=file_id,
                            collection_name=data_source.knowledge_id,
                        ),
                        user=user,
                        db=db,
                    )
                except Exception as e:
                    log.warning(f"Failed to process file {doc.title}: {e}")

                # Add file to knowledge base
                Knowledges.add_file_to_knowledge_by_id(
                    knowledge_id=data_source.knowledge_id,
                    file_id=file_id,
                    user_id=user.id,
                    db=db,
                )

                files_synced += 1

            except Exception as e:
                log.error(f"Error syncing document {doc.title}: {e}")
                errors.append(f"Error syncing {doc.title}: {str(e)}")

        # Update status to idle
        DataSources.update_data_source_status(data_source_id, "idle", db=db)

        return DataSourceSyncResult(
            success=True,
            files_synced=files_synced,
            files_updated=files_updated,
            errors=errors,
            duration_seconds=time.time() - start_time,
        )

    except Exception as e:
        log.exception(f"Sync failed for data source {data_source_id}: {e}")
        DataSources.update_data_source_status(
            data_source_id, "error", str(e), db=db
        )
        return DataSourceSyncResult(
            success=False,
            files_synced=files_synced,
            errors=[str(e)] + errors,
            duration_seconds=time.time() - start_time,
        )
