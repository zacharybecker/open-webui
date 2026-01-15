import logging
import time
from typing import Optional
import uuid

from sqlalchemy.orm import Session
from open_webui.internal.db import Base, get_db_context

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, ForeignKey, String, Text, JSON

log = logging.getLogger(__name__)

####################
# DataSource DB Schema
####################


class DataSource(Base):
    __tablename__ = "data_source"

    id = Column(Text, unique=True, primary_key=True)
    knowledge_id = Column(
        Text, ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Text, nullable=False)

    source_type = Column(String(50), nullable=False)  # "confluence", "jira", "github"
    name = Column(Text, nullable=False)

    config = Column(JSON, nullable=True)  # Source-specific config (space key, repo, etc.)
    credentials = Column(JSON, nullable=True)  # Encrypted API keys/tokens
    sync_config = Column(JSON, nullable=True)  # Sync schedule, sync_mode

    status = Column(String(50), default="idle")  # "idle", "syncing", "error"
    last_sync_at = Column(BigInteger, nullable=True)
    last_sync_error = Column(Text, nullable=True)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class DataSourceModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_id: str
    user_id: str

    source_type: str
    name: str

    config: Optional[dict] = None
    credentials: Optional[dict] = None
    sync_config: Optional[dict] = None

    status: str = "idle"
    last_sync_at: Optional[int] = None
    last_sync_error: Optional[str] = None

    created_at: int
    updated_at: int


####################
# Response Models (without credentials for security)
####################


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_id: str
    user_id: str

    source_type: str
    name: str

    config: Optional[dict] = None
    sync_config: Optional[dict] = None

    status: str = "idle"
    last_sync_at: Optional[int] = None
    last_sync_error: Optional[str] = None

    created_at: int
    updated_at: int


class DataSourceListResponse(BaseModel):
    items: list[DataSourceResponse]
    total: int


####################
# Forms
####################


class DataSourceCreateForm(BaseModel):
    knowledge_id: str
    source_type: str
    name: str
    config: Optional[dict] = None
    credentials: Optional[dict] = None
    sync_config: Optional[dict] = None


class DataSourceUpdateForm(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    credentials: Optional[dict] = None
    sync_config: Optional[dict] = None


class DataSourceSyncResult(BaseModel):
    success: bool
    files_synced: int = 0
    files_updated: int = 0
    files_deleted: int = 0
    errors: list[str] = []
    duration_seconds: float = 0.0


####################
# Available Source Types
####################


class DataSourceTypeInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    config_schema: dict
    credentials_schema: dict
    supports_webhooks: bool = False


####################
# DataSource Table Operations
####################


class DataSourceTable:
    def insert_new_data_source(
        self,
        user_id: str,
        form_data: DataSourceCreateForm,
        db: Optional[Session] = None,
    ) -> Optional[DataSourceModel]:
        with get_db_context(db) as db:
            data_source = DataSourceModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                knowledge_id=form_data.knowledge_id,
                source_type=form_data.source_type,
                name=form_data.name,
                config=form_data.config,
                credentials=form_data.credentials,
                sync_config=form_data.sync_config,
                status="idle",
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )

            try:
                result = DataSource(**data_source.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return DataSourceModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting data source: {e}")
                return None

    def get_data_source_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[DataSourceModel]:
        try:
            with get_db_context(db) as db:
                data_source = db.query(DataSource).filter_by(id=id).first()
                return DataSourceModel.model_validate(data_source) if data_source else None
        except Exception as e:
            log.exception(f"Error getting data source by id: {e}")
            return None

    def get_data_sources_by_knowledge_id(
        self, knowledge_id: str, db: Optional[Session] = None
    ) -> list[DataSourceModel]:
        try:
            with get_db_context(db) as db:
                data_sources = (
                    db.query(DataSource)
                    .filter_by(knowledge_id=knowledge_id)
                    .order_by(DataSource.created_at.desc())
                    .all()
                )
                return [DataSourceModel.model_validate(ds) for ds in data_sources]
        except Exception as e:
            log.exception(f"Error getting data sources by knowledge_id: {e}")
            return []

    def get_data_sources_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[DataSourceModel]:
        try:
            with get_db_context(db) as db:
                data_sources = (
                    db.query(DataSource)
                    .filter_by(user_id=user_id)
                    .order_by(DataSource.updated_at.desc())
                    .all()
                )
                return [DataSourceModel.model_validate(ds) for ds in data_sources]
        except Exception as e:
            log.exception(f"Error getting data sources by user_id: {e}")
            return []

    def get_all_data_sources_with_schedule(
        self, db: Optional[Session] = None
    ) -> list[DataSourceModel]:
        """Get all data sources that have scheduled sync enabled."""
        try:
            with get_db_context(db) as db:
                data_sources = (
                    db.query(DataSource)
                    .filter(DataSource.sync_config.isnot(None))
                    .all()
                )
                # Filter for those with sync_mode != "manual"
                result = []
                for ds in data_sources:
                    ds_model = DataSourceModel.model_validate(ds)
                    if ds_model.sync_config and ds_model.sync_config.get("sync_mode") != "manual":
                        result.append(ds_model)
                return result
        except Exception as e:
            # Check if it's a "table doesn't exist" error - this is expected on first startup
            error_str = str(e).lower()
            if "no such table" in error_str or "does not exist" in error_str:
                log.debug(f"Data source table not yet created (migrations may not have run): {e}")
            else:
                log.exception(f"Error getting scheduled data sources: {e}")
            return []

    def update_data_source_by_id(
        self,
        id: str,
        form_data: DataSourceUpdateForm,
        db: Optional[Session] = None,
    ) -> Optional[DataSourceModel]:
        try:
            with get_db_context(db) as db:
                data_source = db.query(DataSource).filter_by(id=id).first()
                if not data_source:
                    return None

                if form_data.name is not None:
                    data_source.name = form_data.name
                if form_data.config is not None:
                    data_source.config = form_data.config
                if form_data.credentials is not None:
                    data_source.credentials = form_data.credentials
                if form_data.sync_config is not None:
                    data_source.sync_config = form_data.sync_config

                data_source.updated_at = int(time.time())
                db.commit()
                db.refresh(data_source)
                return DataSourceModel.model_validate(data_source)
        except Exception as e:
            log.exception(f"Error updating data source: {e}")
            return None

    def update_data_source_status(
        self,
        id: str,
        status: str,
        error: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[DataSourceModel]:
        try:
            with get_db_context(db) as db:
                data_source = db.query(DataSource).filter_by(id=id).first()
                if not data_source:
                    return None

                data_source.status = status
                data_source.last_sync_error = error
                data_source.updated_at = int(time.time())

                if status == "idle" and error is None:
                    data_source.last_sync_at = int(time.time())

                db.commit()
                db.refresh(data_source)
                return DataSourceModel.model_validate(data_source)
        except Exception as e:
            log.exception(f"Error updating data source status: {e}")
            return None

    def delete_data_source_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> bool:
        try:
            with get_db_context(db) as db:
                db.query(DataSource).filter_by(id=id).delete()
                db.commit()
                return True
        except Exception as e:
            log.exception(f"Error deleting data source: {e}")
            return False

    def delete_data_sources_by_knowledge_id(
        self, knowledge_id: str, db: Optional[Session] = None
    ) -> bool:
        try:
            with get_db_context(db) as db:
                db.query(DataSource).filter_by(knowledge_id=knowledge_id).delete()
                db.commit()
                return True
        except Exception as e:
            log.exception(f"Error deleting data sources by knowledge_id: {e}")
            return False


DataSources = DataSourceTable()
