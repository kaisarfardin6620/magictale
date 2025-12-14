import asyncio
import os
import json
import io
import requests
import copy
from pathlib import Path
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import AsyncOpenAI, RateLimitError, APIError, BadRequestError, AuthenticationError
from elevenlabs.client import AsyncElevenLabs
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pydub import AudioSegment
from django.utils.translation import gettext as _
import logging
from .models import StoryProject, GenerationEvent, StoryPage
from .prompts import get_story_prompts
from elevenlabs import Voice, VoiceSettings
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

LENGTH_TO_TOKENS = {
    "short": 100, 
    "medium": 300, 
    "long": 500, 
}
DEFAULT_TEXT_MODEL = getattr(settings, "AI_TEXT_MODEL", "gpt-4o-2024-08-06")

STYLE_PROMPT_ENHANCERS = {
    "anime": "Japanese anime art style, Studio Ghibli inspired, high quality, vibrant colors, detailed backgrounds, cel shaded, 4k resolution, cinematic lighting, masterpiece",
    "watercolor": "soft watercolor illustration, dreamy pastel colors, hand-painted texture, storybook style",
    "pixar": "3D Pixar animation style, octane render, bright lighting, expressive characters, cute, high detail",
    "papercut": "layered paper cut-out art, depth of field, dimensional shadows, craft texture, whimsical",
    "african_folktale": "traditional African art pattern style, bold geometric shapes, earthy colors, cultural folk art",
    "clay": "stop-motion claymation style, plasticine texture, handmade look, soft lighting",
}

@sync_to_async
def _reload_project(project_id: int) -> StoryProject | None:
    return StoryProject.objects.select_related('parent_project').prefetch_related('pages').filter(pk=project_id).first()

@sync_to_async
def _save_event(project: StoryProject, kind: str, payload: dict):
    GenerationEvent.objects.create(project=project, kind=kind, payload=payload)

@sync_to_async
def _update_project_state(project: StoryProject, status: str = None, progress: int = None, error: str = None, finished=False, **kwargs):
    changed = []
    if status: project.status = status; changed.append("status")
    if progress is not None: project.progress = max(0, min(100, progress)); changed.append("progress")
    if error is not None: project.error = error; changed.append("error")
    if finished: project.finished_at = timezone.now(); changed.append("finished_at")
    for key, value in kwargs.items():
        setattr(project, key, value)
        changed.append(key)
    if changed: project.save(update_fields=changed)
    return project.progress, project.status

@sync_to_async
def _delete_pages(project: StoryProject):
    return project.pages.all().delete()

@sync_to_async
def _create_page(project: StoryProject, index: int, text: str) -> StoryPage:
    return StoryPage.objects.create(project=project, index=index, text=text)

@sync_to_async
def _create_variant_project(parent_project: StoryProject, choice_name: str) -> StoryProject:
    variant = StoryProject.objects.create(
        user=parent_project.user,
        parent_project=parent_project,
        onboarding=parent_project.onboarding,
        child_name=parent_project.child_name,
        age=parent_project.age,
        pronouns=parent_project.pronouns,
        favorite_animal=parent_project.favorite_animal,
        favorite_color=parent_project.favorite_color,
        theme=parent_project.theme,
        art_style=parent_project.art_style,
        language=parent_project.language,
        voice=parent_project.voice,
        length=parent_project.length,
        difficulty=parent_project.difficulty,
        custom_prompt=f"Variant based on choice: {choice_name}",
        model_used=parent_project.model_used,
        status=StoryProject.Status.RUNNING,
        progress=0,
        started_at=timezone.now()
    )
    return variant

async def _send(project_id: int, event: dict):
    layer = get_channel_layer()
    await layer.group_send(f"story_{project_id}", {"type": "progress", "event": event})

def _split_text_into_pages(full_text: str):
    lines = full_text.splitlines()
    paragraphs = [p.strip() for p in lines if p.strip()]
    pages = []
    for i in range(0, len(paragraphs), 3):
        pages.append("\n\n".join(paragraphs[i:i+3]))
    return pages

async def _generate_synopsis_and_tags_async(full_text: str):
    synopsis_prompt = _build_synopsis_prompt(full_text)
    async with AsyncOpenAI(api_key=settings.OPENAI_API_KEY) as openai_client:
        try:
            synopsis_resp = await openai_client.chat.completions.create(
                model=DEFAULT_TEXT_MODEL, messages=[{"role": "user", "content": synopsis_prompt}],
                response_format={"type": "json_object"}, temperature=0.5, timeout=30.0
            )
            metadata = json.loads(synopsis_resp.choices[0].message.content)
            
            if not metadata.get("title"):
                metadata["title"] = _("Magical Story")
            
            if not metadata.get("synopsis") or len(metadata.get("synopsis", "")) < 20:
                metadata["synopsis"] = _("A wonderful and magical adventure.")
            
            if isinstance(metadata.get("tags"), list):
                metadata["tags"] = ", ".join(metadata["tags"])
                
        except Exception as e:
            logger.error(f"Failed to generate/parse synopsis: {e}")
            metadata = {"title": _("My Magical Story"), "synopsis": _("A magical adventure awaits!"), "tags": "Adventure, Magic"}
    return metadata

async def _generate_cover_image_async(metadata: dict, project: StoryProject):
    theme_name = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
    image_prompt = _build_cover_image_prompt(metadata.get("synopsis", theme_name), project)
    async with AsyncOpenAI(api_key=settings.OPENAI_API_KEY) as openai_client:
        try:
            image_resp = await openai_client.images.generate(
                model=settings.AI_IMAGE_MODEL, prompt=image_prompt, n=1, size="1024x1024",
                response_format="url", timeout=120.0
            )
            image_url = image_resp.data[0].url if image_resp.data else ""
        except BadRequestError as e:
            if 'content_policy_violation' in str(e):
                logger.warning(f"Image prompt rejected by safety filter: {e}")
                image_url = "" 
            else:
                logger.error(f"Failed to generate cover image: {e}")
                image_url = ""
        except Exception as e:
            logger.error(f"Failed to generate cover image: {e}")
            image_url = ""
        
    return {"image_url": image_url, "cover_image_url": image_url}

def _build_synopsis_prompt(story_text: str) -> str:
    return (
        "You are a story analyst. Read the following children's story and generate:\n"
        "1. A short, catchy 'title' for the story.\n"
        "2. A one-paragraph 'synopsis' (3-4 sentences).\n"
        "3. 3 relevant single-word 'tags'.\n\n"
        "Return the result ONLY as a JSON object with keys: 'title', 'synopsis', 'tags'.\n"
        "Example format: {{ \"title\": \"The Magic Forest\", \"synopsis\": \"...\", \"tags\": \"Magic, Forest, Fun\" }}\n\n"
        "Story:\n"
        "---\n"
        f"{story_text}\n"
        "---\n"
    )

def _build_cover_image_prompt(synopsis: str, project: StoryProject) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    theme_name = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
    
    base_subject = synopsis if synopsis and len(synopsis) > 20 else theme_name
    
    prompt_subject = f"{base_subject}. Scene is peaceful, cute, whimsical, G-rated, child-friendly. No violence, no weapons, no scary elements."
    
    art_style_key = project.art_style
    art_style_description = STYLE_PROMPT_ENHANCERS.get(art_style_key)
    
    if not art_style_description:
        art_style_description = settings.ART_STYLE_ID_TO_NAME_MAP.get(art_style_key, art_style_key)

    return (prompt_dir / "cover_image_prompt.txt").read_text().format(art_style=art_style_description, prompt_subject=prompt_subject)

@sync_to_async
def _fetch_file_content(path):
    with default_storage.open(path, 'rb') as f:
        return f.read()

async def _generate_audio_for_page(page: StoryPage, project: StoryProject):
    if page.audio_url and default_storage.exists(urlparse(page.audio_url).path.lstrip('/')):
        logger.info(f"Audio already exists for Page {page.index}. Downloading from storage to save credits.")
        try:
            file_path = urlparse(page.audio_url).path.lstrip('/')
            audio_content = await _fetch_file_content(file_path)
            return io.BytesIO(audio_content)
        except Exception as e:
            logger.warning(f"Failed to read existing audio for page {page.index}, re-generating: {e}")

    client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
    
    try:
        voice_id = project.voice or settings.ALL_NARRATOR_VOICES[0]
        
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            text=page.text,
            model_id="eleven_flash_v2_5",
        )
        
        audio_content = b""
        async for chunk in audio_stream:
            audio_content += chunk
        
        if len(audio_content) < 100:
            logger.warning(f"Audio for page {page.index} is empty or invalid. Skipping.")
            return None

        try:
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_content), format="mp3")
            duration_seconds = len(audio_segment) / 1000.0
            page.audio_duration = duration_seconds
        except Exception as e:
            logger.warning(f"Could not calculate duration for page {page.index}: {e}")

        chunk_file_path = f"audio/chunks/story_{project.id}_page_{page.index}.mp3"
        saved_chunk_path = await sync_to_async(default_storage.save)(chunk_file_path, ContentFile(audio_content))
        page.audio_url = await sync_to_async(default_storage.url)(saved_chunk_path)
        
        await sync_to_async(page.save)()
        return io.BytesIO(audio_content)
    except Exception as e:
        logger.error(f"Failed to generate ElevenLabs audio for page {page.index} (Project {project.id}): {e}")
        return None

async def _cleanup_audio_chunks(project_id: int):
    try:
        @sync_to_async
        def delete_chunks():
            try:
                if not hasattr(default_storage, 'listdir'):
                    return 
                dirs, files = default_storage.listdir('audio/chunks')
                for filename in files:
                    if f"story_{project_id}_page_" in filename:
                        default_storage.delete(Path('audio/chunks') / filename)
            except Exception:
                pass
        await delete_chunks()
        logger.info(f"Cleaned up audio chunks for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to clean up audio chunks for project {project_id}: {e}")

async def generate_text_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage1_start", {})
    await _send(project_id, {"status": "running", "progress": 5, "message": _("Whispering to the story spirits...")})

    async with AsyncOpenAI(api_key=settings.OPENAI_API_KEY) as openai_client:
        try:
            temp_project = copy.copy(project)
            temp_project.theme = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
            system_prompt, user_prompt = get_story_prompts(temp_project)

            token_limit = LENGTH_TO_TOKENS.get(project.length, 4000)
            
            model_to_use = project.model_used or DEFAULT_TEXT_MODEL
            if token_limit > 4000 and "gpt-4o" not in model_to_use:
                model_to_use = "gpt-4o-2024-08-06"

            text_resp = await openai_client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "system", "content": str(system_prompt)}, {"role": "user", "content": str(user_prompt)}],
                temperature=0.8, timeout=120.0, max_tokens=token_limit, seed=project_id
            )
            full_text = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
            if not full_text: raise ValueError("AI returned an empty story text.")

            await _update_project_state(project, progress=30, text=full_text, model_used=model_to_use)
            page_texts = _split_text_into_pages(full_text)
            await _delete_pages(project)
            page_objects = [await _create_page(project, i, text) for i, text in enumerate(page_texts, start=1)]
            await _save_event(project, "stage1_done", {"pages_created": len(page_objects)})
            
        except Exception as e:
            await handle_generation_failure(project_id, e)
            raise e

async def generate_metadata_and_cover_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage2_start", {})
    await _send(project_id, {"progress": 40, "message": _("Summarizing and drawing the cover...")})
    
    try:
        metadata = await _generate_synopsis_and_tags_async(project.text)
        image_metadata = await _generate_cover_image_async(metadata, project)
        await _update_project_state(project, progress=65, **metadata, **image_metadata)
        await _save_event(project, "stage2_done", {})
    except Exception as e:
        await handle_generation_failure(project_id, e)
        raise e

async def generate_audio_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage3_start", {})
    await _send(project_id, {"progress": 70, "message": _("Recording narration for each page...")})

    try:
        page_objects = await sync_to_async(list)(project.pages.all())
        
        semaphore = asyncio.Semaphore(2)

        async def generate_with_semaphore(page, project):
            async with semaphore:
                return await _generate_audio_for_page(page, project)

        audio_tasks = [generate_with_semaphore(page, project) for page in page_objects]
        
        audio_chunks = await asyncio.gather(*audio_tasks)

        await _send(project_id, {"progress": 90, "message": _("Combining narration...")})
        combined_audio = None
        for chunk_io in audio_chunks:
            if chunk_io:
                try:
                    chunk_audio = AudioSegment.from_file(chunk_io, format="mp3")
                    combined_audio = chunk_audio if combined_audio is None else combined_audio + chunk_audio
                except Exception as e:
                    logger.error(f"Failed to process audio chunk for project {project_id}: {e}")

        if combined_audio is None:
            logger.warning(f"No valid audio generated for Project {project_id}. Completing text-only.")
            await _update_project_state(project, status="done", progress=100, finished=True)
            await _save_event(project, "done", {"warning": "Audio generation failed"})
            await _send(project_id, {"status": "done", "progress": 100, "message": _("Your story is ready (audio was unavailable).")})
            return

        with io.BytesIO() as buffer:
            combined_audio.export(buffer, format="mp3")
            final_audio_content = buffer.getvalue()

        final_file_path = f"audio/story_{project.id}_full.mp3"
        saved_path = await sync_to_async(default_storage.save)(final_file_path, ContentFile(final_audio_content))
        final_audio_url = await sync_to_async(default_storage.url)(saved_path)

        await _update_project_state(project,
            audio_url=final_audio_url,
            audio_duration_seconds=int(combined_audio.duration_seconds)
        )

        await _update_project_state(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status": "done", "progress": 100, "message": _("Your story is complete!")})
    
    except Exception as e:
        await handle_generation_failure(project_id, e)
        raise e

async def handle_generation_failure(project_id: int, exc: Exception):
    project = await _reload_project(project_id)
    if not project: return

    logger.error(f"GENERATION FAILED for Project {project_id}: {type(exc).__name__} - {str(exc)}")
    error_message = _("An unexpected error occurred while creating your story. Please try again.")
    error_type = type(exc).__name__

    if isinstance(exc, BadRequestError):
        error_message = _("Our story-maker couldn't process this request. Please try a different theme.")
    elif isinstance(exc, AuthenticationError):
        logger.critical("AI API Key is invalid.")
        error_message = _("Service temporarily unavailable.")
    elif isinstance(exc, RateLimitError):
        error_message = _("System is busy. Please try again in a moment.")
    elif isinstance(exc, APIError):
        error_message = _("The AI service is temporarily unavailable. Please try again.")
    elif "elevenlabs" in str(type(exc)).lower() or "elevenlabs" in str(exc).lower():
        error_message = _("We had trouble recording the voice narration. Please try again.")

    await _update_project_state(project, status="failed", error=error_message, finished=True)
    await _save_event(project, "error", {"error": str(exc), "type": error_type})
    await _send(project_id, {"status": "failed", "error": error_message})
    await _cleanup_audio_chunks(project_id)