"""Logging utilities for ORBIT CLI."""

import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler


def setup_logging(
    verbose: bool = False, 
    log_file: Optional[Path] = None,
    console: Optional[Console] = None
) -> logging.Logger:
    """
    Set up enterprise-grade logging with rich formatting.
    
    Args:
        verbose: Enable verbose (DEBUG) logging
        log_file: Optional path to log file
        console: Optional Rich console instance
        
    Returns:
        Configured logger instance
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logger
    logger = logging.getLogger("orbit")
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler with rich formatting
    console_handler = RichHandler(
        console=console or Console(),
        show_time=False,
        show_path=False,
        markup=True
    )
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "orbit") -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (defaults to "orbit")
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)