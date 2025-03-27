import logging
import os
import smtplib
import asyncio
import aiohttp
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, time
from sqlalchemy import select, insert
from jinja2 import Template

from app.models.notification import NotificationType, TriggerConditionType, TimeRestrictedTrigger
from app.models.notification import NotificationTrigger, NotificationEvent
from app.utils.frame_utils import save_frame
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for managing and sending notifications based on triggers"""
    
    def __init__(self):
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.email_from = os.getenv("EMAIL_FROM", self.smtp_username)
        self.last_notification_time = {}  # Dict to track cooldown {trigger_id: timestamp}
    
    async def evaluate_trigger(
        self, 
        trigger: NotificationTrigger, 
        camera_id: int, 
        event_data: Dict[str, Any],
        frame: Optional[Any] = None
    ) -> bool:
        """
        Evaluate if a trigger should fire based on current conditions
        
        Args:
            trigger: The trigger to evaluate
            camera_id: ID of the camera that generated the event
            event_data: Data about the event that might trigger a notification
            frame: Optional frame capture at the time of event
            
        Returns:
            bool: True if trigger should fire, False otherwise
        """
        try:
            # Check if trigger is active
            if not trigger.active:
                return False
            
            # Check camera restriction
            if trigger.camera_id is not None and trigger.camera_id != camera_id:
                return False
            
            # Check cooldown period
            if trigger.last_triggered is not None:
                now = datetime.now()
                time_since_last = (now - trigger.last_triggered).total_seconds()
                if time_since_last < trigger.cooldown_period:
                    return False
                
            if trigger.last_triggered is None:
                logger.info(f"Trigger {trigger.id} has never been triggered before")
            
            # Check time restrictions
            if trigger.time_restriction != TimeRestrictedTrigger.ALWAYS:
                current_time = datetime.now().time()
                
                if trigger.time_start and trigger.time_end:
                    start_hour, start_minute = map(int, trigger.time_start.split(":"))
                    end_hour, end_minute = map(int, trigger.time_end.split(":"))
                    
                    time_start = time(start_hour, start_minute)
                    time_end = time(end_hour, end_minute)
                    
                    # Check if current time is in the specified range
                    in_time_range = (time_start <= current_time <= time_end)
                    
                    # If ONLY_DURING, trigger only if in range
                    # If EXCEPT_DURING, trigger only if NOT in range
                    if trigger.time_restriction == TimeRestrictedTrigger.ONLY_DURING and not in_time_range:
                        return False
                    elif trigger.time_restriction == TimeRestrictedTrigger.EXCEPT_DURING and in_time_range:
                        return False
            
            # Evaluate condition based on condition type
            should_trigger = False
            
            if trigger.condition_type == TriggerConditionType.OCCUPANCY_ABOVE:
                threshold = trigger.condition_params.get("threshold", 0)
                current_occupancy = event_data.get("occupancy", {}).get("current", 0)
                should_trigger = current_occupancy > threshold
                
            elif trigger.condition_type == TriggerConditionType.OCCUPANCY_BELOW:
                threshold = trigger.condition_params.get("threshold", 0)
                current_occupancy = event_data.get("occupancy", {}).get("current", 0)
                should_trigger = current_occupancy < threshold
                
            elif trigger.condition_type == TriggerConditionType.UNREGISTERED_FACE:
                faces = event_data.get("faces", [])
                # An unregistered face has person_id is None or negative
                unregistered_faces = [face for face in faces if face.get("person_id") is None or face.get("person_id") < 0]
                should_trigger = len(unregistered_faces) > 0
                
            elif trigger.condition_type == TriggerConditionType.SPECIFIC_FACE:
                person_id = trigger.condition_params.get("person_id")
                confidence_threshold = trigger.condition_params.get("confidence_threshold", 0.6)
                
                faces = event_data.get("faces", [])
                for face in faces:
                    if (face.get("person_id") == person_id and 
                        face.get("confidence", 0) >= confidence_threshold):
                        should_trigger = True
                        break
                        
            elif trigger.condition_type == TriggerConditionType.TEMPLATE_MATCHED:
                template_id = trigger.condition_params.get("template_id")
                confidence_threshold = trigger.condition_params.get("confidence_threshold", 0.7)
                
                templates = event_data.get("templates", [])
                for template in templates:
                    if (template.get("template_id") == template_id and 
                        template.get("confidence", 0) >= confidence_threshold):
                        should_trigger = True
                        break
            
            return should_trigger
            
        except Exception as e:
            logger.exception(f"Error evaluating trigger {trigger.id}: {str(e)}")
            return False
    
    async def process_trigger(
        self, 
        trigger: NotificationTrigger, 
        camera_id: int, 
        event_data: Dict[str, Any],
        frame: Optional[Any] = None
    ) -> bool:
        """
        Process a trigger and send the notification if needed
        
        Args:
            trigger: The trigger to process
            camera_id: ID of the camera that generated the event
            event_data: Data about the event
            frame: Optional frame capture at the time of event
            
        Returns:
            bool: True if notification was sent, False otherwise
        """
        try:
            # Evaluate if the trigger should fire
            should_trigger = await self.evaluate_trigger(trigger, camera_id, event_data, frame)
            
            if not should_trigger:
                return False
            
            # Save snapshot if we have a frame
            snapshot_path = None
            if frame is not None:
                # Generate a filename based on the event
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"trigger_{trigger.id}_{camera_id}_{timestamp}.jpg"
                
                # Save the frame
                snapshot_path = save_frame(frame, filename, settings.SNAPSHOTS_DIR)
            
            # Create notification event record
            async for session in get_db():
                # Update last triggered time on the trigger
                trigger.last_triggered = datetime.now()
                await session.commit()
                
                # Create notification event
                notification_event = NotificationEvent(
                    trigger_id=trigger.id,
                    camera_id=camera_id,
                    event_data=event_data,
                    snapshot_path=snapshot_path
                )
                
                session.add(notification_event)
                await session.commit()
                await session.refresh(notification_event)
                
                # Send the notification
                success, error = await self.send_notification(
                    trigger, notification_event, frame if snapshot_path else None
                )
                
                # Update notification status
                notification_event.sent_successfully = success
                notification_event.delivery_error = error
                await session.commit()
                
                return success
                
        except Exception as e:
            logger.exception(f"Error processing trigger {trigger.id}: {str(e)}")
            return False
            
    async def send_notification(
        self, 
        trigger: NotificationTrigger, 
        event: NotificationEvent,
        frame: Optional[Any] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Send a notification based on the trigger configuration
        
        Args:
            trigger: The trigger that fired
            event: The notification event record
            frame: Optional frame capture
            
        Returns:
            tuple: (success, error_message)
        """
        try:
            if trigger.notification_type == NotificationType.EMAIL:
                return await self._send_email_notification(trigger, event, frame)
                
            elif trigger.notification_type == NotificationType.TELEGRAM:
                return await self._send_telegram_notification(trigger, event, frame)
                
            elif trigger.notification_type == NotificationType.WEBHOOK:
                return await self._send_webhook_notification(trigger, event, frame)
                
            else:
                return False, f"Unsupported notification type: {trigger.notification_type}"
                
        except Exception as e:
            error_msg = f"Error sending notification: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
            
    async def _send_email_notification(
        self, 
        trigger: NotificationTrigger, 
        event: NotificationEvent,
        frame: Optional[Any] = None
    ) -> tuple[bool, Optional[str]]:
        """Send email notification"""
        try:
            config = trigger.notification_config
            recipients = config.get("recipients", [])
            
            if not recipients:
                return False, "No recipients specified"
                
            # Prepare email content
            subject_template = config.get("subject_template", "CCTV Alert: {{trigger.name}}")
            body_template = config.get("body_template", "Alert triggered by camera {{event.camera_id}} at {{event.timestamp}}.\n\nEvent details: {{event.event_data}}")
            
            # Render templates
            subject = Template(subject_template).render(
                trigger=trigger,
                event=event
            )
            
            body = Template(body_template).render(
                trigger=trigger,
                event=event
            )
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            
            # Attach text
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach snapshot if available
            include_snapshot = config.get("include_snapshot", True)
            if include_snapshot and event.snapshot_path and os.path.exists(event.snapshot_path):
                with open(event.snapshot_path, 'rb') as img_file:
                    img_data = img_file.read()
                    image = MIMEImage(img_data)
                    image.add_header('Content-Disposition', f'attachment; filename="snapshot_{event.id}.jpg"')
                    msg.attach(image)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
                
            return True, None
            
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
            
    async def _send_telegram_notification(
        self, 
        trigger: NotificationTrigger, 
        event: NotificationEvent,
        frame: Optional[Any] = None
    ) -> tuple[bool, Optional[str]]:
        """Send Telegram notification"""
        try:
            if not self.telegram_bot_token:
                return False, "Telegram bot token not configured"
                
            config = trigger.notification_config
            chat_ids = config.get("chat_ids", [])
            
            if not chat_ids:
                return False, "No chat IDs specified"
                
            # Prepare message
            message_template = config.get("message_template", "🚨 CCTV Alert: {{trigger.name}}\n\nTriggered by camera {{event.camera_id}} at {{event.timestamp}}.\n\nEvent details: {{event.event_data}}")
            
            # Render template
            message = Template(message_template).render(
                trigger=trigger,
                event=event
            )
            
            # Send to each chat ID
            include_snapshot = config.get("include_snapshot", True)
            success = True
            error_msg = None
            
            for chat_id in chat_ids:
                try:
                    # If we have a snapshot and should include it
                    if include_snapshot and event.snapshot_path and os.path.exists(event.snapshot_path):
                        # Send photo with caption
                        async with aiohttp.ClientSession() as session:
                            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
                            
                            with open(event.snapshot_path, 'rb') as photo:
                                data = aiohttp.FormData()
                                data.add_field('chat_id', chat_id)
                                data.add_field('caption', message)
                                data.add_field('photo', photo, filename=f"snapshot_{event.id}.jpg")
                                
                                async with session.post(url, data=data) as response:
                                    if response.status != 200:
                                        text = await response.text()
                                        raise Exception(f"Telegram API error: {text}")
                    else:
                        # Send text message only
                        async with aiohttp.ClientSession() as session:
                            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
                            payload = {
                                'chat_id': chat_id,
                                'text': message,
                                'parse_mode': 'HTML'
                            }
                            
                            async with session.post(url, json=payload) as response:
                                if response.status != 200:
                                    text = await response.text()
                                    raise Exception(f"Telegram API error: {text}")
                                    
                except Exception as e:
                    success = False
                    error_msg = f"Error sending to chat {chat_id}: {str(e)}"
                    logger.error(error_msg)
            
            return success, error_msg
            
        except Exception as e:
            error_msg = f"Error sending Telegram notification: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
            
    async def _send_webhook_notification(
        self, 
        trigger: NotificationTrigger, 
        event: NotificationEvent,
        frame: Optional[Any] = None
    ) -> tuple[bool, Optional[str]]:
        """Send webhook notification"""
        try:
            config = trigger.notification_config
            url = config.get("url")
            
            if not url:
                return False, "No webhook URL specified"
                
            headers = config.get("headers", {})
            include_snapshot = config.get("include_snapshot", False)
            
            # Prepare payload
            payload = {
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "event_id": event.id,
                "camera_id": event.camera_id,
                "timestamp": event.timestamp.isoformat(),
                "event_data": event.event_data
            }
            
            # Add snapshot URL if available
            if include_snapshot and event.snapshot_path:
                snapshot_filename = os.path.basename(event.snapshot_path)
                # This assumes your API exposes snapshots via a /static/snapshots/ endpoint
                snapshot_url = f"{settings.API_URL}/static/snapshots/{snapshot_filename}"
                payload["snapshot_url"] = snapshot_url
            
            # Send the webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status < 200 or response.status >= 300:
                        text = await response.text()
                        return False, f"Webhook returned status {response.status}: {text}"
            
            return True, None
            
        except Exception as e:
            error_msg = f"Error sending webhook: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg
    
    async def check_all_triggers(self, camera_id: int, event_data: Dict[str, Any], frame: Optional[Any] = None):
        """
        Check all active triggers for a given camera and event data
        
        Args:
            camera_id: ID of the camera that generated the event
            event_data: Data about the event
            frame: Optional frame capture
        """
        try:
            async for session in get_db():
                # Get all active triggers
                query = select(NotificationTrigger).where(
                    NotificationTrigger.active == True
                )
                result = await session.execute(query)
                triggers = result.scalars().all()
                
                # Process each trigger
                for trigger in triggers:
                    # Process in background to avoid blocking
                    asyncio.create_task(
                        self.process_trigger(trigger, camera_id, event_data, frame)
                    )
                    
        except Exception as e:
            logger.exception(f"Error checking triggers: {str(e)}")

# Singleton instance
_notification_service = None

async def get_notification_service() -> NotificationService:
    """Get or create the notification service singleton"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service