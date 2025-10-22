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
    generate_audio_logic,
    handle_generation_failure,
    openai_client,
)
from django.conf import settings
from pathlib import Path
import time
import requests
import io
from PIL import Image, ImageDraw, ImageFont
import asyncio
from authentication.models import UserProfile
from django.utils.translation import gettext as _

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

@shared_task
def update_user_usage_task(project_id: int):
    try:
        project = StoryProject.objects.select_related('user__profile', 'user__subscription').get(id=project_id)
        profile = project.user.profile
        subscription = project.user.subscription

        if not (subscription.plan == 'master' and subscription.status == 'active'):
            print(f"Updating usage stats for user {project.user.id}")
            
            used_styles = set(profile.used_art_styles.split(',') if profile.used_art_styles else [])
            if project.art_style not in used_styles:
                used_styles.add(project.art_style)
                profile.used_art_styles = ",".join(filter(None, used_styles))

            used_voices = set(profile.used_narrator_voices.split(',') if profile.used_narrator_voices else [])
            if project.voice not in used_voices:
                used_voices.add(project.voice)
                profile.used_narrator_voices = ",".join(filter(None, used_voices))
            
            profile.save(update_fields=['used_art_styles', 'used_narrator_voices'])
            print(f"Successfully updated usage stats for user {project.user.id}")
        else:
            print(f"Skipping usage update for master user {project.user.id}")

    except StoryProject.DoesNotExist:
        print(f"Could not update usage: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An error occurred while updating user usage for project {project_id}: {e}")


@shared_task(bind=True, autoretry_for=RETRYABLE_EXCEPTIONS, retry_kwargs={'max_retries': 3, 'countdown': 60}, on_failure=on_pipeline_failure)
def generate_text_task(self, project_id: int):
    print(f"Starting STAGE 1: TEXT for project {project_id}")
    async_to_sync(generate_text_logic)(project_id)
    print(f"Finished STAGE 1: TEXT for project {project_id}")
    return project_id 

async def remix_text_logic(project_id: int, choice_id: str):

@shared_task(bind=True, autoretry_for=RETRYABLE_EXCEPTIONS, retry_kwargs={'max_retries': 3, 'countdown': 60}, on_failure=on_pipeline_failure)
def remix_text_task(self, project_id: int, choice_id: str):

@shared_task
def watermark_cover_image_task(project_id: int):
    print(f"Checking for watermarking for project {project_id}")
    try:
        project = StoryProject.objects.select_related('user__subscription').get(id=project_id)
        subscription = project.user.subscription

        if not (subscription.plan == 'creator' and subscription.status == 'active'):
            print(f"Skipping watermark for project {project_id} (User is not Tier 1).")
            return project_id

        if not project.cover_image_url:
            print(f"No cover image URL for project {project_id}. Skipping watermark.")
            return project_id

        print(f"Applying watermark for project {project_id} (User is Tier 1).")
        response = requests.get(project.cover_image_url)
        response.raise_for_status()
        
        image_file = io.BytesIO(response.content)
        img = Image.open(image_file).convert("RGBA")
        
        txt_overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_overlay)
        
        text = "MagicTale AI"
        try:
            font = ImageFont.truetype("static/fonts/arial.ttf", 40)
        except IOError:
            font = ImageFont.load_default()
        
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = (img.width - text_width - 20, img.height - text_height - 20)
        
        draw.text(position, text, font=font, fill=(255, 255, 255, 128))
        
        watermarked_img = Image.alpha_composite(img, txt_overlay)
        
        buffer = io.BytesIO()
        watermarked_img.convert('RGB').save(buffer, format='JPEG', quality=90)
        buffer.seek(0)
        
        from urllib.parse import urlparse
        file_path = urlparse(project.cover_image_url).path.lstrip('/')
        
        new_file = ContentFile(buffer.read())
        default_storage.delete(file_path)
        default_storage.save(file_path, new_file)
        
        print(f"Successfully watermarked cover image for project {project_id}")

    except StoryProject.DoesNotExist:
        print(f"Error watermarking image: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An unexpected error occurred during watermarking for project {project_id}: {e}")
        
    return project_id 

@shared_task
def optimize_cover_image_task(project_id: int):
    print(f"Starting image optimization for project {project_id}")
    try:
        project = StoryProject.objects.get(id=project_id)
        if not project.cover_image_url:
            return project_id 
            
        response = requests.get(project.cover_image_url)
        response.raise_for_status()
        image_file = io.BytesIO(response.content)
        img = Image.open(image_file)
        buffer = io.BytesIO()
        img.convert('RGB').save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)
        
        from urllib.parse import urlparse
        original_path = urlparse(project.cover_image_url).path.lstrip('/')
        
        new_file = ContentFile(buffer.read())
        default_storage.delete(original_path)
        default_storage.save(original_path, new_file)
        
        print(f"Successfully optimized image for project {project_id}")
    except Exception as e:
        print(f"An unexpected error occurred during image optimization for project {project_id}: {e}")
        
    return project_id

@shared_task(bind=True, autoretry_for=RETRYABLE_EXCEPTIONS, retry_kwargs={'max_retries': 3, 'countdown': 60}, on_failure=on_pipeline_failure)
def generate_metadata_and_cover_task(self, project_id: int):
    from .engine import generate_metadata_and_cover_logic
    print(f"Starting STAGE 2: METADATA/COVER for project {project_id}")
    async_to_sync(generate_metadata_and_cover_logic)(project_id)
    print(f"Finished STAGE 2: METADATA/COVER for project {project_id}")
    chain(optimize_cover_image_task.s(), watermark_cover_image_task.s()).apply_async(args=[project_id])
    
    return project_id

@shared_task(bind=True, autoretry_for=RETRYABLE_EXCEPTIONS, retry_kwargs={'max_retries': 3, 'countdown': 120}, on_failure=on_pipeline_failure)
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
        
        update_user_usage_task.delay(project_id)
        
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

def start_story_remix_pipeline(project_id: int, choice_id: str):
    pipeline = chain(
        remix_text_task.s(project_id, choice_id),
        generate_audio_task.s()
    )
    print(f"Dispatching REMIX pipeline for project {project_id}")
    pipeline.apply_async()

@shared_task(bind=True)
def generate_pdf_task(self, project_id: int, base_url: str):
    print(f"Starting PDF generation for project {project_id}")
    try:
        project = StoryProject.objects.get(id=project_id)
        context = {"project": project}
        html_string = render_to_string("ai/story_pdf_template.html", context)
        pdf_file_bytes = HTML(string=html_string).write_pdf()
        file_path = f'pdfs/story_{project.id}_{project.child_name}.pdf'
        default_storage.save(file_path, ContentFile(pdf_file_bytes))
        relative_pdf_url = default_storage.url(file_path)
        full_pdf_url = f"{base_url}{relative_pdf_url}"
        print(f"Successfully generated and saved PDF for project {project_id} at {full_pdf_url}")
        notification_payload = {
            "type": "progress", 
            "event": {
                "status": "pdf_ready",
                "message": _("Your story PDF is ready for download!"),
                "pdf_url": full_pdf_url
            }
        }
        async_to_sync(_send)(project_id, notification_payload)
    except StoryProject.DoesNotExist:
        print(f"Error generating PDF: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An unexpected error occurred during PDF generation for project {project_id}: {e}")
        raise