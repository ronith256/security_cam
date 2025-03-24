import logging
import logging.handlers
import os
from typing import Optional

def setup_logging(
    log_file: Optional[str] = "cctv_monitoring.log",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG
):
    """Set up detailed logging configuration for the application"""
    # Create logs directory if it doesn't exist
    if log_file and not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Clear existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    verbose_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    
    # Console handler (less detailed for clarity)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (more detailed for debugging)
    if log_file:
        log_path = os.path.join('logs', log_file)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(verbose_formatter)
        root_logger.addHandler(file_handler)
    
    # Set more restrictive levels for some verbose modules
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    
    # But ensure our app's loggers are properly configured
    logging.getLogger('app').setLevel(logging.DEBUG)
    
    # Return the configured logger
    return root_logger

# Sample usage in app.main
# if __name__ == "__main__":
#     setup_logging()
#     logger = logging.getLogger(__name__)
#     logger.info("Application starting")