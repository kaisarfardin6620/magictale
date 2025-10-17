import openai
from celery import shared_task, chain
from asgiref.sync import async_to_sync
from django.utils.translation import gettext_lazy as _
from weasyprint import HTML
from django.template.loader import render_to_string
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import StoryProject
from .engine import (
    _reload_project,
    _update_project_state,
    _save_event,
    _send,
    _cleanup_audio_chunks,
    generate_text_logic,
    generate_metadata_and_cover_logic,
    generate_audio_logic,
    handle_generation_failure
)
import time
import requests
import io
from PIL import Image


RETRYABLE_EXCEPTIONS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)

def on_pipeline_failure(self, exc, task_id, args, kwargs, einfo):
    project_id = args[0]
    print(f"PIPELINE FAILED: Task {self.name} for project {project_id} failed permanently. Reason: {exc}")
    async_to_sync(handle_generation_failure)(project_id, exc)


@shared_task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    on_failure=on_pipeline_failure
)
def generate_text_task(self, project_id: int):
    """Celery Task - STAGE 1: Generates the story text and pages."""
    print(f"Starting STAGE 1: TEXT for project {project_id}")
    async_to_sync(generate_text_logic)(project_id)
    print(f"Finished STAGE 1: TEXT for project {project_id}")
    return project_id

@shared_task
def optimize_cover_image_task(project_id: int):
    print(f"Starting image optimization for project {project_id}")
    try:
        project = StoryProject.objects.get(id=project_id)
        if not project.cover_image_url:
            print(f"No cover image URL for project {project_id}. Skipping optimization.")
            return

        response = requests.get(project.cover_image_url)
        response.raise_for_status()
        image_file = io.BytesIO(response.content)
        img = Image.open(image_file)
        buffer = io.BytesIO()
        img.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)
        optimized_file_path = f'images/covers/optimized/story_{project.id}_cover.jpg'
        new_file = ContentFile(buffer.read())
        saved_path = default_storage.save(optimized_file_path, new_file)
        project.cover_image_url = default_storage.url(saved_path)
        project.save(update_fields=['cover_image_url'])
        print(f"Successfully optimized and updated cover image for project {project_id}")
    except StoryProject.DoesNotExist:
        print(f"Error optimizing image: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An unexpected error occurred during image optimization for project {project_id}: {e}")
@shared_task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    on_failure=on_pipeline_failure
)
def generate_metadata_and_cover_task(self, project_id: int):
    print(f"Starting STAGE 2: METADATA/COVER for project {project_id}")
    async_to_sync(generate_metadata_and_cover_logic)(project_id)
    print(f"Finished STAGE 2: METADATA/COVER for project {project_id}")
    optimize_cover_image_task.delay(project_id)
    return project_id

@shared_task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 3, 'countdown': 120}, 
    on_failure=on_pipeline_failure
)
def generate_audio_task(self, project_id: int):
    print(f"Starting STAGE 3: AUDIO for project {project_id}")
    async_to_sync(generate_audio_logic)(project_id)
    print(f"Finished STAGE 3: AUDIO for project {project_id}")
    async_to_sync(_cleanup_audio_chunks)(project_id)
    project = async_to_sync(_reload_project)(project_id)
    if project and project.started_at and project.finished_at:
        duration = project.finished_at - project.started_at
        total_seconds = duration.total_seconds()
        print(f"Project {project_id} generation pipeline complete. Total time: {total_seconds:.2f} seconds.")
    else:
        print(f"Project {project_id} generation pipeline complete.")
        
    return project_id

def start_story_generation_pipeline(project_id: int):
    pipeline = chain(
        generate_text_task.s(project_id),
        generate_metadata_and_cover_task.s(),
        generate_audio_task.s()
    )
    print(f"Dispatching generation pipeline for project {project_id}")
    pipeline.apply_async()



@shared_task(bind=True)
def generate_pdf_task(self, project_id: int):
    print(f"Starting PDF generation for project {project_id}")
    try:
        project = StoryProject.objects.get(id=project_id)
        context = {"project": project}
        html_string = render_to_string("ai/story_pdf_template.html", context)
        pdf_file_bytes = HTML(string=html_string).write_pdf()

        file_path = f'pdfs/story_{project.id}_{project.child_name}.pdf'
        default_storage.save(file_path, ContentFile(pdf_file_bytes))
        pdf_url = default_storage.url(file_path)

        print(f"Successfully generated and saved PDF for project {project_id} at {pdf_url}")

        notification_payload = {
            "type": "progress", 
            "event": {
                "status": "pdf_ready",
                "message": _("Your story PDF is ready for download!"),
                "pdf_url": pdf_url
            }
        }
        async_to_sync(_send)(project_id, notification_payload)

    except StoryProject.DoesNotExist:
        print(f"Error generating PDF: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An unexpected error occurred during PDF generation for project {project_id}: {e}")
        raise