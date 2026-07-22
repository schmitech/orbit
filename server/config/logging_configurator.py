"""
Logging configuration utilities for the inference server.

This module handles all logging setup and configuration, including:
- Initial basic logging setup
- Full logging configuration from config files
- Console and file logging setup
- JSON and text formatters
- Log rotation and retention
- Logger-specific configurations
"""

import os
import time
import logging
import logging.handlers
from typing import Dict, Any
from pythonjsonlogger import jsonlogger
from utils import is_true_value


class _UvicornLoggerNameFilter(logging.Filter):
    """Normalize uvicorn logger names so they match the project logging style."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.error":
            record.name = "server.inference_server"
        elif record.name == "uvicorn.access":
            record.name = "server.inference_server.access"
        return True


class LoggingConfigurator:
    """
    Handles all aspects of logging configuration for the inference server.
    
    This class is responsible for:
    - Setting up initial basic logging during startup
    - Configuring full logging based on application configuration
    - Managing console and file handlers
    - Setting up log rotation and retention
    - Configuring JSON and text formatters
    - Managing logger-specific settings
    """
    
    @staticmethod
    def setup_initial_logging() -> logging.Logger:
        """
        Set up basic logging configuration before loading the full config.
        
        This method initializes a basic logging configuration that will be used
        until the full configuration is loaded. It ensures that critical startup
        messages are properly logged.
        
        The basic configuration includes:
        - Console output
        - Timestamp formatting
        - Log level set to INFO
        - Basic log format
        
        This is a temporary setup that will be replaced by the full logging
        configuration once the config is loaded.
        
        Returns:
            Logger instance for the calling module
        """
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        )
        
        # Set specific logger levels for more detailed debugging
        logging.getLogger('clients.ollama_client').setLevel(logging.DEBUG)
        
        return logging.getLogger(__name__)
    
    @staticmethod
    def setup_full_logging(config: Dict[str, Any]) -> logging.Logger:
        """
        Configure logging based on the application configuration.
        
        This method sets up the full logging configuration based on the loaded
        configuration file. It supports:
        - Console and file logging
        - JSON and text formats
        - Log rotation
        - Custom log levels
        - Warning capture
        
        Configuration options include:
        - Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        - Log format (JSON or text)
        - Log file settings (path, rotation, size limits)
        - Console output settings
        - Warning capture settings
        
        The configuration is applied to the root logger and can be overridden
        for specific loggers if needed.
        
        Args:
            config: The application configuration dictionary
            
        Returns:
            Logger instance for the calling module
        """
        log_config = config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        
        # Configure root logger first
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Clear existing handlers to prevent duplicates
        root_logger.handlers.clear()
        
        # Create formatters based on configuration
        text_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        json_formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
        
        # Configure console logging
        handlers = log_config.get('handlers', {})
        console_enabled = is_true_value(handlers.get('console', {}).get('enabled', True))
        if console_enabled:
            console_handler = logging.StreamHandler()
            console_format = handlers.get('console', {}).get('format', 'text')
            console_handler.setFormatter(json_formatter if console_format == 'json' else text_formatter)
            console_handler.setLevel(log_level)
            console_handler.addFilter(_UvicornLoggerNameFilter())
            root_logger.addHandler(console_handler)

        # Configure file logging
        file_enabled = is_true_value(handlers.get('file', {}).get('enabled', True))
        if file_enabled:
            LoggingConfigurator._setup_file_logging(
                root_logger, handlers.get('file', {}),
                json_formatter, text_formatter, log_level
            )
        
        # Set propagation for root logger
        root_logger.propagate = is_true_value(log_config.get('propagate', False))
        
        # Capture warnings if configured - do this BEFORE configuring specific loggers
        # so that py.warnings logger is created and can be configured
        if is_true_value(log_config.get('capture_warnings', True)):
            logging.captureWarnings(True)
        
        # Configure specific loggers (including py.warnings which was just created)
        if 'loggers' in log_config:
            LoggingConfigurator._configure_specific_loggers(log_config)
        
        # Get a new logger instance for the calling module
        logger = logging.getLogger(__name__)
        logger.propagate = is_true_value(log_config.get('propagate', False))
        logger.info("Logging configuration completed")
        
        return logger
    
    # How long a dead worker's log family is kept around before being swept,
    # and the hard cap on how many dead families can be retained regardless
    # of age (a fast crash-loop could otherwise pile up many families within
    # the retention window). A crashed worker's own logs are usually the
    # main evidence for diagnosing why it died - deleting them the instant
    # its replacement starts (i.e. immediately) would erase that evidence
    # before an operator ever gets to look.
    _DEAD_WORKER_LOG_RETENTION_SECONDS = 24 * 60 * 60
    _DEAD_WORKER_LOG_MAX_RETAINED_FAMILIES = 20

    @staticmethod
    def _cleanup_stale_worker_logs(log_dir: str, filename: str) -> None:
        """
        Remove `<filename>.worker<pid>*` families belonging to dead PIDs,
        once they're old enough (or there are too many retained) that
        keeping them stops being useful. Called from a worker's own
        startup, before it opens its own file, so recycled workers don't
        leave orphaned log families accumulating forever (see the call
        site for why that matters) - while still giving an operator a
        window to inspect a crashed worker's logs before they're swept.

        Safe to run concurrently from multiple workers starting at once —
        a file already removed by another worker's sweep just isn't there
        to remove again.
        """
        prefix = f"{filename}.worker"
        try:
            entries = os.listdir(log_dir)
        except OSError:
            return

        # Map each matching filename to the PID it belongs to (not just a
        # startswith check - "worker123" is a substring-prefix of
        # "worker1234", and family membership must be exact).
        name_pids: Dict[str, int] = {}
        pid_liveness: Dict[int, bool] = {}
        for name in entries:
            if not name.startswith(prefix):
                continue
            pid_str = name[len(prefix):].split(".", 1)[0]
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            name_pids[name] = pid
            if pid == os.getpid() or pid in pid_liveness:
                continue
            try:
                os.kill(pid, 0)
                pid_liveness[pid] = True
            except ProcessLookupError:
                pid_liveness[pid] = False
            except PermissionError:
                # Some other process owns this PID and is still alive -
                # leave its family alone.
                pid_liveness[pid] = True

        dead_pids = {pid for pid in pid_liveness if not pid_liveness[pid]}
        if not dead_pids:
            return

        # A family's age is how long it's been since its most recently
        # written file was touched, not when the process died - a worker
        # that logged nothing for hours before crashing shouldn't get a
        # fresh 24h grace period starting from "now."
        last_written: Dict[int, float] = {}
        for name, pid in name_pids.items():
            if pid not in dead_pids:
                continue
            try:
                mtime = os.path.getmtime(os.path.join(log_dir, name))
            except OSError:
                continue
            last_written[pid] = max(last_written.get(pid, 0.0), mtime)

        now = time.time()
        cutoff = now - LoggingConfigurator._DEAD_WORKER_LOG_RETENTION_SECONDS
        pids_to_remove = {pid for pid, mtime in last_written.items() if mtime < cutoff}

        # Backstop: even within the retention window, cap how many dead
        # families can pile up (e.g. during a fast crash loop) by dropping
        # the oldest ones beyond the cap.
        still_retained = sorted(
            (pid for pid in last_written if pid not in pids_to_remove),
            key=lambda pid: last_written[pid],
        )
        overflow = len(still_retained) - LoggingConfigurator._DEAD_WORKER_LOG_MAX_RETAINED_FAMILIES
        if overflow > 0:
            pids_to_remove.update(still_retained[:overflow])

        if not pids_to_remove:
            return

        for name, pid in name_pids.items():
            if pid in pids_to_remove:
                try:
                    os.remove(os.path.join(log_dir, name))
                except OSError:
                    pass

    @staticmethod
    def _setup_file_logging(
        root_logger: logging.Logger,
        file_config: Dict[str, Any],
        json_formatter: logging.Formatter,
        text_formatter: logging.Formatter,
        log_level: int
    ) -> None:
        """
        Set up file logging with rotation support.
        
        Args:
            root_logger: The root logger instance
            file_config: File logging configuration
            json_formatter: JSON formatter instance
            text_formatter: Text formatter instance
            log_level: Logging level
        """
        log_dir = file_config.get('directory', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        filename = file_config.get('filename', 'orbit.log')

        # Under performance.workers > 1, each worker independently builds its
        # own InferenceServer (see inference_server.py's run()) and would
        # otherwise open its own RotatingFileHandler/TimedRotatingFileHandler
        # on this SAME path. Concurrent line writes are fine, but rotation
        # isn't: each process decides on its own when to rotate and renames
        # the file independently, so two processes can race and one keeps
        # writing into a now-orphaned file, silently losing log lines.
        # ORBIT_SUPERVISOR_PID is set (by inference_server.py's run(), before
        # spawning workers) on the supervisor and inherited by every worker;
        # it differs from a worker's own PID but matches the supervisor's.
        # Give each worker its own file — and thus its own independent
        # rotation state — by suffixing it with the worker's PID. The
        # supervisor keeps the plain filename (its own logging was already
        # configured before run() knows whether workers > 1, and it writes
        # far less volume — mostly startup/shutdown — so no race there).
        supervisor_pid = os.environ.get('ORBIT_SUPERVISOR_PID')
        if supervisor_pid is not None and int(supervisor_pid) != os.getpid():
            # backup_count bounds each worker's own rotation history, but not
            # the number of PID-scoped families that can pile up over the
            # server's lifetime: when uvicorn's Multiprocess replaces a
            # crashed/unhealthy worker, the old PID's family is never touched
            # again by anyone (its process is gone, and no other process owns
            # that filename) — repeated recycling would accumulate one
            # unbounded, never-cleaned family per dead worker and eventually
            # exhaust disk. Sweep them away before creating our own file.
            LoggingConfigurator._cleanup_stale_worker_logs(log_dir, filename)
            filename = f"{filename}.worker{os.getpid()}"

        log_file = os.path.join(log_dir, filename)

        # Set up rotating file handler
        if file_config.get('rotation') == 'midnight':
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=file_config.get('backup_count', 30),
                encoding='utf-8'
            )
        else:
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=file_config.get('max_size_mb', 10) * 1024 * 1024,
                backupCount=file_config.get('backup_count', 30),
                encoding='utf-8'
            )
        
        file_format = file_config.get('format', 'text')
        file_handler.setFormatter(json_formatter if file_format == 'json' else text_formatter)
        file_handler.setLevel(log_level)
        file_handler.addFilter(_UvicornLoggerNameFilter())
        root_logger.addHandler(file_handler)
    
    @staticmethod
    def _configure_specific_loggers(log_config: Dict[str, Any]) -> None:
        """
        Configure specific loggers with custom settings.

        Args:
            log_config: The logging configuration dictionary
        """
        for logger_name, logger_config in log_config['loggers'].items():
            logger = logging.getLogger(logger_name)
            
            # Handle disabled flag first
            if is_true_value(logger_config.get('disabled', False)):
                logger.disabled = True
                logger.setLevel(logging.CRITICAL)
                continue
            
            logger_level = getattr(logging, logger_config.get('level', 'INFO').upper())
            logger.setLevel(logger_level)
            
            # Allow override of propagate per logger
            if 'propagate' in logger_config:
                logger.propagate = is_true_value(logger_config.get('propagate'))
            else:
                logger.propagate = is_true_value(log_config.get('propagate', False))
