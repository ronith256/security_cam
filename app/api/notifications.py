from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.models.notification import (
    NotificationTrigger, NotificationEvent, NotificationTriggerCreate, 
    NotificationTriggerUpdate, NotificationTriggerResponse, NotificationEventResponse
)
from app.services.notification_service import get_notification_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/triggers", response_model=List[NotificationTriggerResponse])
async def get_triggers(
    active: Optional[bool] = None,
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all notification triggers with optional filtering"""
    query = select(NotificationTrigger)
    
    if active is not None:
        query = query.where(NotificationTrigger.active == active)
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    triggers = result.scalars().all()
    return triggers

@router.post("/triggers", response_model=NotificationTriggerResponse)
async def create_trigger(
    trigger: NotificationTriggerCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new notification trigger"""
    try:
        db_trigger = NotificationTrigger(
            name=trigger.name,
            description=trigger.description,
            active=trigger.active,
            condition_type=trigger.condition_type,
            condition_params=trigger.condition_params,
            time_restriction=trigger.time_restriction,
            time_start=trigger.time_start,
            time_end=trigger.time_end,
            camera_id=trigger.camera_id,
            cooldown_period=trigger.cooldown_period,
            notification_type=trigger.notification_type,
            notification_config=trigger.notification_config
        )
        
        db.add(db_trigger)
        await db.commit()
        await db.refresh(db_trigger)
        
        return db_trigger
    except Exception as e:
        logger.exception(f"Error creating trigger: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/triggers/{trigger_id}", response_model=NotificationTriggerResponse)
async def get_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific notification trigger by ID"""
    trigger = await db.get(NotificationTrigger, trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trigger

@router.put("/triggers/{trigger_id}", response_model=NotificationTriggerResponse)
async def update_trigger(
    trigger_id: int,
    trigger_update: NotificationTriggerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a notification trigger"""
    trigger = await db.get(NotificationTrigger, trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    # Update fields
    update_data = trigger_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(trigger, key, value)
    
    await db.commit()
    await db.refresh(trigger)
    
    return trigger

@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a notification trigger"""
    trigger = await db.get(NotificationTrigger, trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    await db.delete(trigger)
    await db.commit()
    
    return {"message": f"Trigger {trigger_id} deleted successfully"}

@router.post("/triggers/{trigger_id}/toggle")
async def toggle_trigger(
    trigger_id: int,
    active: bool,
    db: AsyncSession = Depends(get_db)
):
    """Toggle a trigger's active status"""
    trigger = await db.get(NotificationTrigger, trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    trigger.active = active
    await db.commit()
    
    return {"message": f"Trigger {trigger_id} {'activated' if active else 'deactivated'} successfully"}

@router.get("/events", response_model=List[NotificationEventResponse])
async def get_notification_events(
    trigger_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    successful_only: bool = False,
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get notification events with optional filtering"""
    query = select(NotificationEvent)
    
    # Apply filters
    if trigger_id is not None:
        query = query.where(NotificationEvent.trigger_id == trigger_id)
    
    if camera_id is not None:
        query = query.where(NotificationEvent.camera_id == camera_id)
    
    if start_date is not None:
        query = query.where(NotificationEvent.timestamp >= start_date)
    
    if end_date is not None:
        query = query.where(NotificationEvent.timestamp <= end_date)
    
    if successful_only:
        query = query.where(NotificationEvent.sent_successfully == True)
    
    # Order by timestamp descending (newest first)
    query = query.order_by(NotificationEvent.timestamp.desc())
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    events = result.scalars().all()
    
    return events

@router.get("/events/{event_id}", response_model=NotificationEventResponse)
async def get_notification_event(
    event_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific notification event by ID"""
    event = await db.get(NotificationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@router.post("/test/{trigger_id}")
async def test_trigger(
    trigger_id: int,
    test_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Test a trigger with sample data"""
    trigger = await db.get(NotificationTrigger, trigger_id)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    # Get the notification service
    notification_service = await get_notification_service()
    
    # Skip the cooldown check for test notifications
    original_last_triggered = trigger.last_triggered
    trigger.last_triggered = None
    
    camera_id = test_data.get("camera_id", 1)
    event_data = test_data.get("event_data", {})
    
    # Process the trigger
    success = await notification_service.process_trigger(
        trigger, camera_id, event_data, None
    )
    
    # Restore the original last_triggered timestamp
    trigger.last_triggered = original_last_triggered
    await db.commit()
    
    if success:
        return {"message": "Test notification sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test notification")

@router.get("/stats")
async def get_notification_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics"""
    # Set default date range if not provided (last 7 days)
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=7)
    
    # Get total count of events
    total_query = select(func.count(NotificationEvent.id)).where(
        NotificationEvent.timestamp >= start_date,
        NotificationEvent.timestamp <= end_date
    )
    
    # Get count of successful events
    success_query = select(func.count(NotificationEvent.id)).where(
        NotificationEvent.timestamp >= start_date,
        NotificationEvent.timestamp <= end_date,
        NotificationEvent.sent_successfully == True
    )
    
    # Get count of failed events
    failed_query = select(func.count(NotificationEvent.id)).where(
        NotificationEvent.timestamp >= start_date,
        NotificationEvent.timestamp <= end_date,
        NotificationEvent.sent_successfully == False
    )
    
    # Execute queries
    total_result = await db.execute(total_query)
    success_result = await db.execute(success_query)
    failed_result = await db.execute(failed_query)
    
    total_count = total_result.scalar() or 0
    success_count = success_result.scalar() or 0
    failed_count = failed_result.scalar() or 0
    
    # Get counts by trigger type
    triggers_query = select(
        NotificationTrigger.id,
        NotificationTrigger.name,
        NotificationTrigger.condition_type,
        func.count(NotificationEvent.id).label("event_count")
    ).outerjoin(
        NotificationEvent, 
        NotificationEvent.trigger_id == NotificationTrigger.id
    ).where(
        NotificationEvent.timestamp >= start_date,
        NotificationEvent.timestamp <= end_date
    ).group_by(
        NotificationTrigger.id
    )
    
    triggers_result = await db.execute(triggers_query)
    trigger_stats = []
    
    for row in triggers_result:
        trigger_stats.append({
            "trigger_id": row.id,
            "trigger_name": row.name,
            "condition_type": row.condition_type.value,
            "event_count": row.event_count
        })
    
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": (success_count / total_count * 100) if total_count > 0 else 0,
        "trigger_stats": trigger_stats
    }