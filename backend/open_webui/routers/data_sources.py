"""
API router for external data source management.

Provides endpoints for CRUD operations on data sources,
credential validation, and sync operations.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.data_sources import (
    DataSources,
    DataSourceCreateForm,
    DataSourceUpdateForm,
    DataSourceResponse,
    DataSourceListResponse,
    DataSourceSyncResult,
    DataSourceTypeInfo,
)
from open_webui.models.knowledge import Knowledges
from open_webui.models.files import Files, FileForm
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import has_access
from open_webui.utils.crypto import encrypt_credentials, decrypt_credentials, mask_credentials
from open_webui.constants import ERROR_MESSAGES
from open_webui.routers.retrieval import process_file, ProcessFileForm

# Import connectors to register them
from open_webui.data_sources import (
    get_connector,
    get_available_source_types,
    DocumentContent,
)
from open_webui.data_sources.confluence import ConfluenceConnector
from open_webui.data_sources.jira import JiraConnector
from open_webui.data_sources.github import GitHubConnector

log = logging.getLogger(__name__)

router = APIRouter()


def model_to_response(data_source) -> DataSourceResponse:
    """Convert DataSourceModel to DataSourceResponse (without credentials)."""
    return DataSourceResponse(
        id=data_source.id,
        knowledge_id=data_source.knowledge_id,
        user_id=data_source.user_id,
        source_type=data_source.source_type,
        name=data_source.name,
        config=data_source.config,
        sync_config=data_source.sync_config,
        status=data_source.status,
        last_sync_at=data_source.last_sync_at,
        last_sync_error=data_source.last_sync_error,
        created_at=data_source.created_at,
        updated_at=data_source.updated_at,
    )


############################
# Get Available Source Types
############################


@router.get("/types", response_model=list[DataSourceTypeInfo])
async def get_source_types(user=Depends(get_verified_user)):
    """Get list of available data source types."""
    return get_available_source_types()


############################
# Get Data Sources by Knowledge ID
############################


@router.get("/knowledge/{knowledge_id}", response_model=DataSourceListResponse)
async def get_data_sources_by_knowledge(
    knowledge_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Get all data sources for a knowledge base."""
    # Check access to knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=knowledge_id, db=db)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "read", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    data_sources = DataSources.get_data_sources_by_knowledge_id(knowledge_id, db=db)
    return DataSourceListResponse(
        items=[model_to_response(ds) for ds in data_sources],
        total=len(data_sources),
    )


############################
# Create Data Source
############################


class CreateDataSourceRequest(BaseModel):
    knowledge_id: str
    source_type: str
    name: str
    config: Optional[dict] = None
    credentials: Optional[dict] = None
    sync_config: Optional[dict] = None


@router.post("/create", response_model=DataSourceResponse)
async def create_data_source(
    form_data: CreateDataSourceRequest,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Create a new data source linked to a knowledge base."""
    # Check access to knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=form_data.knowledge_id, db=db)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "write", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    # Verify source type exists
    connector = get_connector(form_data.source_type)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source type: {form_data.source_type}",
        )

    # Encrypt credentials if provided
    encrypted_credentials = None
    if form_data.credentials:
        encrypted_credentials = {"encrypted": encrypt_credentials(form_data.credentials)}

    # Create data source
    data_source = DataSources.insert_new_data_source(
        user_id=user.id,
        form_data=DataSourceCreateForm(
            knowledge_id=form_data.knowledge_id,
            source_type=form_data.source_type,
            name=form_data.name,
            config=form_data.config,
            credentials=encrypted_credentials,
            sync_config=form_data.sync_config or {"sync_mode": "manual"},
        ),
        db=db,
    )

    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create data source",
        )

    return model_to_response(data_source)


############################
# Get Data Source
############################


@router.get("/{id}", response_model=DataSourceResponse)
async def get_data_source(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Get a data source by ID."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check access via knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=data_source.knowledge_id, db=db)
    if not knowledge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated knowledge base not found",
        )

    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "read", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return model_to_response(data_source)


############################
# Update Data Source
############################


class UpdateDataSourceRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    credentials: Optional[dict] = None
    sync_config: Optional[dict] = None


@router.post("/{id}/update", response_model=DataSourceResponse)
async def update_data_source(
    id: str,
    form_data: UpdateDataSourceRequest,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Update a data source."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check access via knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=data_source.knowledge_id, db=db)
    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "write", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    # Encrypt credentials if provided
    encrypted_credentials = None
    if form_data.credentials:
        encrypted_credentials = {"encrypted": encrypt_credentials(form_data.credentials)}

    updated = DataSources.update_data_source_by_id(
        id=id,
        form_data=DataSourceUpdateForm(
            name=form_data.name,
            config=form_data.config,
            credentials=encrypted_credentials,
            sync_config=form_data.sync_config,
        ),
        db=db,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update data source",
        )

    return model_to_response(updated)


############################
# Delete Data Source
############################


@router.delete("/{id}", response_model=bool)
async def delete_data_source(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Delete a data source."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check access via knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=data_source.knowledge_id, db=db)
    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "write", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return DataSources.delete_data_source_by_id(id, db=db)


############################
# Validate Credentials
############################


class ValidateCredentialsRequest(BaseModel):
    source_type: str
    credentials: dict


class ValidateCredentialsResponse(BaseModel):
    valid: bool
    message: Optional[str] = None
    user_info: Optional[dict] = None


@router.post("/validate", response_model=ValidateCredentialsResponse)
async def validate_credentials(
    form_data: ValidateCredentialsRequest,
    user=Depends(get_verified_user),
):
    """Validate credentials for a data source type."""
    connector = get_connector(form_data.source_type)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source type: {form_data.source_type}",
        )

    result = connector.validate_credentials(form_data.credentials)
    return ValidateCredentialsResponse(
        valid=result.valid,
        message=result.message,
        user_info=result.user_info,
    )


############################
# List Available Sources
############################


class ListSourcesRequest(BaseModel):
    source_type: str
    credentials: dict
    search: Optional[str] = None


class SourceInfoResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/sources", response_model=list[SourceInfoResponse])
async def list_available_sources(
    form_data: ListSourcesRequest,
    user=Depends(get_verified_user),
):
    """List available sources (spaces, projects, repos) for a connector."""
    connector = get_connector(form_data.source_type)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source type: {form_data.source_type}",
        )

    sources = connector.list_available_sources(
        form_data.credentials, form_data.search
    )

    return [
        SourceInfoResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            url=s.url,
            metadata=s.metadata,
        )
        for s in sources
    ]


############################
# Sync Data Source
############################


def _decrypt_data_source_credentials(data_source) -> Optional[dict]:
    """Decrypt credentials from a data source."""
    if not data_source.credentials:
        return None
    encrypted = data_source.credentials.get("encrypted")
    if not encrypted:
        return data_source.credentials
    return decrypt_credentials(encrypted)


async def _sync_data_source(
    request: Request,
    data_source_id: str,
    user,
    db: Session,
) -> DataSourceSyncResult:
    """Perform sync for a data source."""
    import uuid

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

        # Fetch content
        for doc in connector.fetch_content(
            config=data_source.config or {},
            credentials=credentials,
            last_sync_at=data_source.last_sync_at,
        ):
            try:
                # Create a file from the document content
                file_id = str(uuid.uuid4())

                # Create file record
                file_form = FileForm(
                    id=file_id,
                    filename=f"{doc.title}.txt",
                    path="",
                    data={"content": doc.content},
                    meta={
                        "name": doc.title,
                        "content_type": "text/plain",
                        "size": len(doc.content),
                        "external_id": doc.external_id,
                        "external_url": doc.url,
                        "data_source_id": data_source_id,
                        "source": data_source.source_type,
                        **doc.metadata,
                    },
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


@router.post("/{id}/sync", response_model=DataSourceSyncResult)
async def sync_data_source(
    request: Request,
    id: str,
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Trigger sync for a data source."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check access via knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=data_source.knowledge_id, db=db)
    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "write", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    # Check if already syncing
    if data_source.status == "syncing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sync already in progress",
        )

    # Perform sync (could be moved to background task for large syncs)
    result = await _sync_data_source(request, id, user, db)
    return result


############################
# Get Sync Status
############################


class SyncStatusResponse(BaseModel):
    status: str
    last_sync_at: Optional[int] = None
    last_sync_error: Optional[str] = None


@router.get("/{id}/status", response_model=SyncStatusResponse)
async def get_sync_status(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Get sync status for a data source."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Check access via knowledge base
    knowledge = Knowledges.get_knowledge_by_id(id=data_source.knowledge_id, db=db)
    if not (
        user.role == "admin"
        or knowledge.user_id == user.id
        or has_access(user.id, "read", knowledge.access_control, db=db)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    return SyncStatusResponse(
        status=data_source.status,
        last_sync_at=data_source.last_sync_at,
        last_sync_error=data_source.last_sync_error,
    )


############################
# Webhook Endpoint
############################


@router.post("/webhook/{source_type}/{id}")
async def handle_webhook(
    request: Request,
    source_type: str,
    id: str,
    db: Session = Depends(get_session),
):
    """Handle incoming webhook from external source."""
    data_source = DataSources.get_data_source_by_id(id, db=db)
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    if data_source.source_type != source_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source type mismatch",
        )

    connector = get_connector(source_type)
    if not connector or not connector.supports_webhooks():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhooks not supported for this source type",
        )

    # TODO: Implement webhook handling
    # This would verify the webhook signature, parse the payload,
    # and trigger incremental sync for the affected content

    return {"status": "received"}
