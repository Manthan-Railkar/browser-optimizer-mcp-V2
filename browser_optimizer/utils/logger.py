from loguru import logger 
from browser_optimizer.config.settings import settings 
import sys 

logger.remove() 
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level}</level> | "
        "{message}"
    ),
)

__all__ = ["logger"]