import logging

def configure_mongodb_logging():
    """Configure MongoDB logging to suppress debug messages"""
    # Set all MongoDB-related loggers to WARNING level
    logging.getLogger('pymongo').setLevel(logging.WARNING)
    logging.getLogger('motor').setLevel(logging.WARNING)
    logging.getLogger('mongodb').setLevel(logging.WARNING)
    
    # Set specific MongoDB loggers to WARNING level
    for logger_name in [
        'pymongo.topology',
        'pymongo.connection',
        'pymongo.server',
        'pymongo.pool',
        'pymongo.monitor',
        'pymongo.periodic_executor'
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING) 