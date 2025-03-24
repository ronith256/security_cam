import asyncio
import logging
from typing import Dict, List, Any, Callable, Optional, Union
from collections import defaultdict

logger = logging.getLogger(__name__)

class EventEmitter:
    """
    Simple event emitter for asynchronous event handling.
    Allows components to subscribe to and emit events.
    """
    def __init__(self):
        self._handlers = defaultdict(list)
        self._loop = None
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Get the event loop"""
        if not self._loop or self._loop.is_closed():
            self._loop = asyncio.get_event_loop()
        return self._loop
    
    def on(self, event: str, handler: Callable) -> None:
        """
        Register an event handler
        
        Args:
            event: Event name
            handler: Callback function or coroutine
        """
        self._handlers[event].append(handler)
    
    def off(self, event: str, handler: Optional[Callable] = None) -> None:
        """
        Remove an event handler
        
        Args:
            event: Event name
            handler: Handler to remove, if None, removes all handlers for the event
        """
        if handler is None:
            self._handlers[event] = []
        else:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]
    
    def emit(self, event: str, data: Any = None) -> None:
        """
        Emit an event
        
        Args:
            event: Event name
            data: Event data
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Schedule coroutine in the event loop
                    asyncio.create_task(handler(event, data))
                else:
                    # Call synchronous handler
                    handler(event, data)
            except Exception as e:
                logger.exception(f"Error in event handler for {event}: {str(e)}")
    
    async def emit_async(self, event: str, data: Any = None) -> List[Any]:
        """
        Emit an event and wait for all async handlers to complete
        
        Args:
            event: Event name
            data: Event data
            
        Returns:
            List of handler results
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return []
        
        results = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Await coroutine
                    result = await handler(event, data)
                else:
                    # Call synchronous handler
                    result = handler(event, data)
                results.append(result)
            except Exception as e:
                logger.exception(f"Error in event handler for {event}: {str(e)}")
                results.append(None)
        
        return results
    
    def listeners(self, event: str) -> List[Callable]:
        """Get all handlers for an event"""
        return self._handlers.get(event, [])
    
    def has_listeners(self, event: str) -> bool:
        """Check if an event has any handlers"""
        return bool(self._handlers.get(event, []))
    
    def clear(self) -> None:
        """Remove all event handlers"""
        self._handlers.clear()