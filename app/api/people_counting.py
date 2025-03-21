from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.models.camera import Camera
from app.models.event import Event, EventType, OccupancyResponse
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/occupancy", response_model=List[OccupancyResponse])
async def get_current_occupancy(
    camera_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get current room occupancy for all or a specific camera"""
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    results = []
    
    # If camera_id is provided, get occupancy for that camera only
    if camera_id is not None:
        # Check if camera exists
        camera = await db.get(Camera, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # Get occupancy
        occupancy = 0
        last_updated = datetime.now()
        
        if camera_id in camera_manager.cameras:
            occupancy = camera_manager.cameras[camera_id].get_current_occupancy()
            
            # Get last occupancy event timestamp
            query = select(Event.timestamp).where(
                Event.camera_id == camera_id,
                Event.event_type == EventType.OCCUPANCY_CHANGED
            ).order_by(desc(Event.timestamp)).limit(1)
            
            result = await db.execute(query)
            timestamp = result.scalar_one_or_none()
            
            if timestamp:
                last_updated = timestamp
        
        results.append({
            "camera_id": camera_id,
            "camera_name": camera.name,
            "current_count": occupancy,
            "last_updated": last_updated
        })
    
    # Otherwise, get occupancy for all cameras
    else:
        # Get all cameras
        query = select(Camera)
        result = await db.execute(query)
        cameras = result.scalars().all()
        
        for camera in cameras:
            occupancy = 0
            last_updated = datetime.now()
            
            if camera.id in camera_manager.cameras:
                occupancy = camera_manager.cameras[camera.id].get_current_occupancy()
                
                # Get last occupancy event timestamp
                query = select(Event.timestamp).where(
                    Event.camera_id == camera.id,
                    Event.event_type == EventType.OCCUPANCY_CHANGED
                ).order_by(desc(Event.timestamp)).limit(1)
                
                result = await db.execute(query)
                timestamp = result.scalar_one_or_none()
                
                if timestamp:
                    last_updated = timestamp
            
            results.append({
                "camera_id": camera.id,
                "camera_name": camera.name,
                "current_count": occupancy,
                "last_updated": last_updated
            })
    
    return results

@router.get("/history")
async def get_occupancy_history(
    camera_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    interval: Optional[str] = Query("1h", regex="^[0-9]+[mhd]$"),  # e.g., 15m, 1h, 1d
    db: AsyncSession = Depends(get_db)
):
    """Get occupancy history for a camera over time"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Set default date range if not provided (last 24 hours)
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(hours=24)
    
    # Get all occupancy events in the time range
    query = select(Event).where(
        Event.camera_id == camera_id,
        Event.event_type == EventType.OCCUPANCY_CHANGED,
        Event.timestamp >= start_date,
        Event.timestamp <= end_date
    ).order_by(Event.timestamp)
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    # Parse interval
    interval_value = int(interval[:-1])
    interval_unit = interval[-1]
    
    if interval_unit == 'm':
        delta = timedelta(minutes=interval_value)
    elif interval_unit == 'h':
        delta = timedelta(hours=interval_value)
    elif interval_unit == 'd':
        delta = timedelta(days=interval_value)
    else:
        delta = timedelta(hours=1)  # Default to 1 hour
    
    # Group events by interval
    history = []
    current_time = start_date
    while current_time <= end_date:
        next_time = current_time + delta
        
        # Find the last event before next_time
        last_event = None
        for event in events:
            if event.timestamp >= current_time and event.timestamp < next_time:
                last_event = event
        
        if last_event:
            history.append({
                "timestamp": last_event.timestamp,
                "count": last_event.occupancy_count
            })
        elif history:
            # If no event in this interval, use the last known count
            history.append({
                "timestamp": current_time,
                "count": history[-1]["count"]
            })
        else:
            # If no previous data, assume zero
            history.append({
                "timestamp": current_time,
                "count": 0
            })
        
        current_time = next_time
    
    return {
        "camera_id": camera_id,
        "camera_name": camera.name,
        "start_date": start_date,
        "end_date": end_date,
        "interval": interval,
        "data": history
    }

@router.get("/entries-exits")
async def get_entries_exits(
    camera_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get entry and exit counts for a camera"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Set default date range if not provided (last 24 hours)
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(hours=24)
    
    # Get entry events
    entry_query = select(func.count(Event.id)).where(
        Event.camera_id == camera_id,
        Event.event_type == EventType.PERSON_ENTERED,
        Event.timestamp >= start_date,
        Event.timestamp <= end_date
    )
    
    # Get exit events
    exit_query = select(func.count(Event.id)).where(
        Event.camera_id == camera_id,
        Event.event_type == EventType.PERSON_EXITED,
        Event.timestamp >= start_date,
        Event.timestamp <= end_date
    )
    
    entry_result = await db.execute(entry_query)
    exit_result = await db.execute(exit_query)
    
    entry_count = entry_result.scalar_one_or_none() or 0
    exit_count = exit_result.scalar_one_or_none() or 0
    
    # Get current occupancy
    camera_manager = await get_camera_manager()
    current_occupancy = 0
    
    if camera_id in camera_manager.cameras:
        current_occupancy = camera_manager.cameras[camera_id].get_current_occupancy()
    
    return {
        "camera_id": camera_id,
        "camera_name": camera.name,
        "start_date": start_date,
        "end_date": end_date,
        "entry_count": entry_count,
        "exit_count": exit_count,
        "current_occupancy": current_occupancy
    }

@router.post("/{camera_id}/reset")
async def reset_people_counter(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reset the people counter for a camera"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Reset counter
    if camera_id in camera_manager.cameras:
        processor = camera_manager.cameras[camera_id]
        if processor.people_counter:
            processor.people_counter.reset_counts()
            return {"message": f"People counter for camera {camera_id} reset successfully"}
    
    raise HTTPException(status_code=400, detail="Failed to reset people counter")

@router.post("/{camera_id}/line-position")
async def set_line_position(
    camera_id: int,
    position: float,
    db: AsyncSession = Depends(get_db)
):
    """Set the virtual line position for counting"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Validate position
    if position < 0 or position > 1:
        raise HTTPException(status_code=400, detail="Position must be between 0 and 1")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Set line position
    if camera_id in camera_manager.cameras:
        processor = camera_manager.cameras[camera_id]
        if processor.people_counter:
            processor.people_counter.set_line_position(position)
            return {"message": f"Line position for camera {camera_id} set to {position}"}
    
    raise HTTPException(status_code=400, detail="Failed to set line position")