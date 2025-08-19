# ai/tasks.py

import openai
from celery import shared_task
from asgiref.sync import async_to_sync
from .engine import run_generation_async

# Define which specific, temporary exceptions from the OpenAI library should trigger a retry.
# We DON'T want to retry on permanent errors like invalid authentication or bad prompts.
RETRYABLE_EXCEPTIONS = (
    openai.APITimeoutError,      # The request took too long.
    openai.APIConnectionError,   # There was a network issue.
    openai.RateLimitError,       # We're sending requests too fast.
    openai.InternalServerError,  # OpenAI's servers had a temporary problem.
)

@shared_task(
    bind=True, 
    autoretry_for=RETRYABLE_EXCEPTIONS, 
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def run_generation_task(self, project_id: int):
    """
    Celery task with automatic retries for common OpenAI API issues.
    
    - autoretry_for: If one of the specified exceptions happens, Celery won't fail the task.
                     Instead, it will automatically try again.
    - retry_kwargs: 
        - 'max_retries': 3 = It will try a total of 4 times (the initial attempt + 3 retries).
        - 'countdown': 60 = It will wait 60 seconds before the next attempt.
    """
    print(f"Starting generation task for project {project_id}. Attempt: {self.request.retries + 1}")
    try:
        async_to_sync(run_generation_async)(project_id)
    except Exception as e:
        # This 'except' block will only be reached if:
        # 1. An exception occurs that is NOT in RETRYABLE_EXCEPTIONS (e.g., a bug in your own code).
        # 2. All 3 retries have been used up and the task still fails.
        print(f"Task for project {project_id} failed permanently after retries: {e}")
        # Re-raising the exception is important to mark the task as 'FAILURE' in your Celery monitor.
        raise