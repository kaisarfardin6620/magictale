import openai
from celery import shared_task, chain, group
from asgiref.sync import async_to_sync
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
    _create_variant_project,
    LENGTH_TO_TOKENS
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
from notifications.tasks import create_and_send_notification_task
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlparse
from openai import AsyncOpenAI

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
        subscription = project.user.subscription

        if not (subscription.plan == 'master' and subscription.status == 'active'):
            print(f"Skipping usage update, now handled in serializer, for user {project.user.id}")
        else:
            print(f"Skipping usage update for master user {project.user.id}")

    except StoryProject.DoesNotExist:
        print(f"Could not update usage: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An error occurred while checking user usage for project {project_id}: {e}")

@shared_task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 5, 'countdown': 10, 'max_countdown': 60},
    on_failure=on_pipeline_failure
)
def generate_text_task(self, project_id: int):
    print(f"Starting STAGE 1: TEXT for project {project_id}")
    async_to_sync(generate_text_logic)(project_id)
    print(f"Finished STAGE 1: TEXT for project {project_id}")
    
    generate_variants_task.delay(project_id)
    
    return project_id 

@shared_task
def generate_variants_task(project_id: int):
    try:
        project = StoryProject.objects.select_related('user__subscription').get(id=project_id)
        
        user_plan = project.user.subscription.plan
        user_status = project.user.subscription.status
        
        print(f"DEBUG: Checking Variants for Project {project_id}. Plan: '{user_plan}', Status: '{user_status}'")

        if user_plan != 'master':
            print(f"STOP: Variants blocked. User is '{user_plan}', required 'master'.")
            return
        
        if user_status != 'active':
            print(f"STOP: Variants blocked. Subscription status is '{user_status}', required 'active'.")
            return
        
        if project.parent_project:
            print(f"STOP: This is already a variant project.")
            return

        print(f"START: Fan-out generation for project {project_id} (Master Plan Validated)")
        
        theme_data = settings.ALL_THEMES_DATA.get(project.theme)
        if not theme_data or not theme_data.get('choices'):
            return

        choices = theme_data['choices'][:3]
        
        for choice in choices:
            variant_project = async_to_sync(_create_variant_project)(project, choice['name'])
            start_story_remix_pipeline(variant_project.id, choice['id'])
            
    except StoryProject.DoesNotExist:
        pass
    except Exception as e:
        print(f"Error generating variants for project {project_id}: {e}")


async def remix_text_logic(project_id: int, choice_id: str):
    openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "remix_start", {"choice_id": choice_id})
    await _send(project_id, {"status": "running", "progress": 5, "message": _("Changing the story's path...")})

    choice_description = "A new adventure."
    for theme_data in settings.ALL_THEMES_DATA.values():
        for choice in theme_data['choices']:
            if choice['id'] == choice_id:
                choice_description = choice['description']
                break

    prompt_dir = Path(__file__).parent / "prompts"
    remix_prompt_template = (prompt_dir / "remix_prompt.txt").read_text()
    
    if project.parent_project and project.parent_project.text:
        original_paragraphs = project.parent_project.text.split('\n\n')
    else:
        original_paragraphs = project.text.split('\n\n')
        
    first_half_text = "\n\n".join(original_paragraphs[:len(original_paragraphs)//2])

    remix_prompt = remix_prompt_template.format(
        original_story_beginning=first_half_text,
        choice_description=choice_description
    )
    
    token_limit = LENGTH_TO_TOKENS.get(project.length, 1000)

    text_resp = await openai_client.chat.completions.create(
        model=project.model_used or "gpt-4o-2024-08-06",
        messages=[{"role": "user", "content": remix_prompt}],
        temperature=0.8,
        timeout=90.0,
        max_tokens=token_limit
    )
    
    new_second_half = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
    if not new_second_half: raise ValueError("AI returned an empty remixed story.")
    
    new_full_text = first_half_text + "\n\n" + new_second_half

    await _update_project_state(project, progress=30, text=new_full_text)
    
    from .engine import _split_text_into_pages, _delete_pages, _create_page
    page_texts = _split_text_into_pages(new_full_text)
    await _delete_pages(project)
    await asyncio.gather(*[_create_page(project, i, text) for i, text in enumerate(page_texts, start=1)])
    await _save_event(project, "remix_done", {"pages_created": len(page_texts)})


@shared_task(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 5, 'countdown': 10, 'max_countdown': 60},
    on_failure=on_pipeline_failure
)
def remix_text_task(self, project_id: int, choice_id: str):
    print(f"Starting REMIX: TEXT for project {project_id}")
    async_to_sync(remix_text_logic)(project_id, choice_id)
    print(f"Finished REMIX: TEXT for project {project_id}")
    return project_id

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

@shared_task(bind=True, autoretry_for=RETRYABLE_EXCEPTIONS, retry_kwargs={'max_retries': 5, 'countdown': 120, 'max_countdown': 1000}, on_failure=on_pipeline_failure)
def generate_metadata_and_cover_task(self, project_id: int):
    from .engine import generate_metadata_and_cover_logic
    print(f"Starting STAGE 2: METADATA/COVER for project {project_id}")
    async_to_sync(generate_metadata_and_cover_logic)(project_id)
    print(f"Finished STAGE 2: METADATA/COVER for project {project_id}")
    
    pipeline = chain(
        optimize_cover_image_task.s(project_id),
        watermark_cover_image_task.s()
    )
    pipeline.apply_async()
    
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
        
        notification_data = {"type": "story_complete", "story_id": project.id}
        create_and_send_notification_task.delay(
            project.user.id,
            "Your Story is Ready!",
            f"The adventure for '{project.child_name}' is complete and waiting for you.",
            data=notification_data
        )

        
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
        generate_metadata_and_cover_task.s(),
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
        
        pdf_file_bytes = HTML(string=html_string, base_url=base_url).write_pdf() 
        
        file_path = f'pdfs/story_{project.id}_{project.child_name}.pdf'
        default_storage.save(file_path, ContentFile(pdf_file_bytes))
        relative_pdf_url = default_storage.url(file_path)
        
        if relative_pdf_url.startswith('http'):
            full_pdf_url = relative_pdf_url
        else:
            full_pdf_url = f"{base_url}{relative_pdf_url}"
        
        print(f"Successfully generated and saved PDF for project {project_id} at {full_pdf_url}")
        notification_data = {"type": "pdf_ready", "story_id": project.id, "pdf_url": full_pdf_url}
        create_and_send_notification_task.delay(
            project.user.id,
            "PDF Ready for Download",
            f"Your PDF for the story '{project.child_name}' is ready.",
            data=notification_data
        )
        
    except StoryProject.DoesNotExist:
        print(f"Error generating PDF: StoryProject with id={project_id} not found.")
    except Exception as e:
        print(f"An unexpected error occurred during PDF generation for project {project_id}: {e}")
        raise

@shared_task
def cleanup_stalled_projects_task():
    print("Running cleanup for stalled/failed projects older than 24 hours...")
    try:
        cutoff_time = timezone.now() - timedelta(hours=24)
        
        stale_projects = StoryProject.objects.filter(
            created_at__lt=cutoff_time,
            status__in=['failed', 'pending', 'running', 'canceled']
        )
        
        count = stale_projects.count()
        if count == 0:
            print("No stale projects found to clean up.")
            return

        for project in stale_projects:
            try:
                if project.cover_image_url:
                    path = urlparse(project.cover_image_url).path.lstrip('/')
                    if default_storage.exists(path):
                        default_storage.delete(path)
                
                if project.audio_url:
                    path = urlparse(project.audio_url).path.lstrip('/')
                    if default_storage.exists(path):
                        default_storage.delete(path)
                
                for page in project.pages.all():
                    if page.audio_url:
                        path = urlparse(page.audio_url).path.lstrip('/')
                        if default_storage.exists(path):
                            default_storage.delete(path)
                
                async_to_sync(_cleanup_audio_chunks)(project.id)
                
            except Exception as e:
                print(f"Error cleaning up files for project {project.id}: {e}")
        
        stale_projects.delete()
        print(f"Successfully cleaned up {count} stalled projects.")
        
    except Exception as e:
        print(f"Fatal error during cleanup task: {e}")