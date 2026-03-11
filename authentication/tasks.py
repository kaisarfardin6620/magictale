from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

@shared_task
def flush_expired_tokens_task():
    try:
        call_command('flushexpiredtokens')
        logger.info("Successfully flushed expired JWT tokens.")
    except Exception as e:
        logger.error(f"Failed to flush expired JWT tokens: {e}")