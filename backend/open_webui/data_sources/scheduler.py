"""
Scheduled sync service for external data sources.

Provides periodic syncing of data sources based on their configured schedules.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from open_webui.models.data_sources import DataSources, DataSourceModel
from open_webui.utils.crypto import decrypt_credentials
from open_webui.data_sources import get_connector
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

# Track the scheduler task
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_running = False


def get_sync_interval_seconds(sync_mode: str) -> int:
    """Get sync interval in seconds based on sync mode."""
    intervals = {
        "hourly": 3600,          # 1 hour
        "daily": 86400,          # 24 hours
        "every_6_hours": 21600,  # 6 hours
        "every_12_hours": 43200, # 12 hours
        "weekly": 604800,        # 7 days
    }
    return intervals.get(sync_mode, 0)


def _get_next_cron_fire_time(cron_expression: str, last_sync_at: Optional[int]) -> Optional[datetime]:
    """Return next cron fire time after the last sync time."""
    try:
        trigger = CronTrigger.from_crontab(cron_expression)
    except Exception as e:
        log.warning(f"Invalid cron expression for data source schedule: {cron_expression} ({e})")
        return None

    last_fire_time = (
        datetime.fromtimestamp(last_sync_at) if last_sync_at else None
    )
    reference_time = last_fire_time or datetime.now()
    return trigger.get_next_fire_time(last_fire_time, reference_time)


def should_sync_now(data_source: DataSourceModel) -> bool:
    """Check if a data source should be synced based on its schedule."""
    if not data_source.sync_config:
        return False

    sync_mode = data_source.sync_config.get("sync_mode", "manual")
    if sync_mode == "manual":
        return False

    if sync_mode == "custom":
        cron_expression = data_source.sync_config.get("cron")
        if not cron_expression:
            return False
        next_fire_time = _get_next_cron_fire_time(
            cron_expression, data_source.last_sync_at
        )
        if not next_fire_time:
            return False
        return datetime.now() >= next_fire_time

    interval = get_sync_interval_seconds(sync_mode)
    if interval == 0:
        return False

    # Check if enough time has passed since last sync
    last_sync = data_source.last_sync_at or 0
    current_time = int(time.time())

    return (current_time - last_sync) >= interval


async def sync_data_source_background(
    data_source_id: str,
    app_state,
) -> None:
    """
    Sync a data source in the background.
    
    This is called by the scheduler for automatic syncs.
    """
    from open_webui.internal.db import get_db_context
    
    try:
        with get_db_context() as db:
            data_source = DataSources.get_data_source_by_id(data_source_id, db=db)
            if not data_source:
                log.warning(f"Data source {data_source_id} not found for scheduled sync")
                return

            # Skip if already syncing
            if data_source.status == "syncing":
                log.debug(f"Data source {data_source_id} already syncing, skipping")
                return

            # Update status to syncing
            DataSources.update_data_source_status(data_source_id, "syncing", db=db)

            try:
                # Get connector
                connector = get_connector(data_source.source_type)
                if not connector:
                    raise ValueError(f"Unknown source type: {data_source.source_type}")

                # Decrypt credentials
                credentials = None
                if data_source.credentials:
                    encrypted = data_source.credentials.get("encrypted")
                    if encrypted:
                        credentials = decrypt_credentials(encrypted)
                    else:
                        credentials = data_source.credentials

                if not credentials:
                    raise ValueError("Missing credentials")

                # Count synced files for logging
                files_synced = 0

                # Fetch content
                for doc in connector.fetch_content(
                    config=data_source.config or {},
                    credentials=credentials,
                    last_sync_at=data_source.last_sync_at,
                ):
                    # TODO: In a full implementation, we would:
                    # 1. Create/update file records
                    # 2. Process files for vector DB
                    # 3. Link files to knowledge base
                    files_synced += 1

                log.info(
                    f"Scheduled sync completed for data source {data_source_id}: "
                    f"{files_synced} files synced"
                )

                # Update status to idle (success)
                DataSources.update_data_source_status(data_source_id, "idle", db=db)

            except Exception as e:
                log.exception(f"Scheduled sync failed for data source {data_source_id}: {e}")
                DataSources.update_data_source_status(
                    data_source_id, "error", str(e), db=db
                )

    except Exception as e:
        log.exception(f"Error in background sync for {data_source_id}: {e}")


async def scheduler_loop(app_state, check_interval: int = 300):
    """
    Main scheduler loop that checks for data sources that need syncing.
    
    Args:
        app_state: FastAPI app state
        check_interval: How often to check for scheduled syncs (default 5 minutes)
    """
    global _scheduler_running
    
    log.info("Data source scheduler started")
    _scheduler_running = True

    while _scheduler_running:
        try:
            from open_webui.internal.db import get_db_context
            
            with get_db_context() as db:
                # Get all data sources with scheduled sync
                data_sources = DataSources.get_all_data_sources_with_schedule(db=db)

                for ds in data_sources:
                    if should_sync_now(ds):
                        log.info(f"Triggering scheduled sync for data source: {ds.id}")
                        # Run sync in background task
                        asyncio.create_task(
                            sync_data_source_background(ds.id, app_state)
                        )

        except Exception as e:
            log.exception(f"Error in scheduler loop: {e}")

        # Wait before next check
        await asyncio.sleep(check_interval)

    log.info("Data source scheduler stopped")


def start_scheduler(app_state, check_interval: int = 300):
    """Start the data source sync scheduler."""
    global _scheduler_task
    
    if _scheduler_task is not None and not _scheduler_task.done():
        log.warning("Scheduler already running")
        return

    _scheduler_task = asyncio.create_task(
        scheduler_loop(app_state, check_interval)
    )
    log.info("Data source scheduler task created")


def stop_scheduler():
    """Stop the data source sync scheduler."""
    global _scheduler_running, _scheduler_task
    
    _scheduler_running = False
    
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        _scheduler_task = None
        log.info("Data source scheduler stopped")


def is_scheduler_running() -> bool:
    """Check if the scheduler is currently running."""
    return _scheduler_running and _scheduler_task is not None and not _scheduler_task.done()
