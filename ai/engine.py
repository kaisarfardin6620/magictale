import asyncio
import os
import json
import io
from pathlib import Path
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import AsyncOpenAI, RateLimitError, APIError
from elevenlabs.client import AsyncElevenLabs
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pydub import AudioSegment
from django.utils.translation import gettext as _
import logging
from .models import StoryProject, GenerationEvent, StoryPage
from .prompts import get_story_prompts
from elevenlabs import Voice, VoiceSettings

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
elevenlabs_client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

logger = logging.getLogger(__name__)

LENGTH_TO_TOKENS = {
    "short": 4000, "medium": 7000, "long": 10000,
}
DEFAULT_TEXT_MODEL = getattr(settings, "AI_TEXT_MODEL", "gpt-4-turbo")

async def api_with_retry(async_func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return await async_func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"API call failed after {max_retries} attempts: {e}")
                raise e
            wait_time = 2 ** attempt
            logger.warning(f"API call failed, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)

@sync_to_async
def _reload_project(project_id: int) -> StoryProject | None:
    return StoryProject.objects.prefetch_related('pages').filter(pk=project_id).first()

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
    synopsis_resp = await api_with_retry(
        openai_client.chat.completions.create,
        model=DEFAULT_TEXT_MODEL, messages=[{"role": "user", "content": synopsis_prompt}],
        response_format={"type": "json_object"}, temperature=0.5, timeout=30.0
    )
    try:
        metadata = json.loads(synopsis_resp.choices[0].message.content)
        if not metadata.get("synopsis") or len(metadata.get("synopsis", "")) < 20:
            metadata["synopsis"] = _("A wonderful and magical adventure.")
        if isinstance(metadata.get("tags"), list):
             metadata["tags"] = ", ".join(metadata["tags"])
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        logger.error(f"Failed to parse synopsis JSON: {e}")
        metadata = {"synopsis": _("A magical adventure awaits!"), "tags": "Adventure, Magic"}
    return metadata

async def _generate_cover_image_async(metadata: dict, project: StoryProject):
    theme_name = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
    image_prompt = _build_cover_image_prompt(metadata.get("synopsis", theme_name), project)
    image_resp = await api_with_retry(
        openai_client.images.generate,
        model=settings.AI_IMAGE_MODEL, prompt=image_prompt, n=1, size="1024x1024",
        response_format="url", timeout=120.0
    )
    image_url = image_resp.data[0].url if image_resp.data else ""
    return {"image_url": image_url, "cover_image_url": image_url}

def _build_synopsis_prompt(story_text: str) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    return (prompt_dir / "synopsis_prompt.txt").read_text().format(story_text=story_text)

def _build_cover_image_prompt(synopsis: str, project: StoryProject) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    theme_name = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
    prompt_subject = synopsis if synopsis and len(synopsis) > 20 else theme_name
    art_style_name = settings.ART_STYLE_ID_TO_NAME_MAP.get(project.art_style, project.art_style)
    return (prompt_dir / "cover_image_prompt.txt").read_text().format(art_style=art_style_name, prompt_subject=prompt_subject)

async def _generate_audio_for_page(page: StoryPage, project: StoryProject):
    try:
        voice_id = project.voice or "IKne3meq5aSn9XLyUdCD"
        
        audio_stream = await elevenlabs_client.text_to_speech.convert(
            voice_id=voice_id,
            text=page.text,
            model_id="eleven_multilingual_v2",
        )
        
        audio_content = b"".join([chunk async for chunk in audio_stream])
        
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
            if hasattr(default_storage, 'listdir'):
                try: dirs, files = default_storage.listdir('audio/chunks')
                except Exception: return
                for filename in files:
                    if f"story_{project_id}_page_" in filename:
                        default_storage.delete(Path('audio/chunks') / filename)
        await delete_chunks()
        logger.info(f"Cleaned up audio chunks for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to clean up audio chunks for project {project_id}: {e}")

async def generate_text_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage1_start", {})
    await _send(project_id, {"status": "running", "progress": 5, "message": str(_("Whispering to the story spirits..."))})

    from copy import deepcopy
    temp_project = deepcopy(project)
    temp_project.theme = settings.THEME_ID_TO_NAME_MAP.get(project.theme, project.theme)
    system_prompt, user_prompt = get_story_prompts(temp_project)

    token_limit = LENGTH_TO_TOKENS.get(project.length, 2000)
    text_resp = await api_with_retry(
        openai_client.chat.completions.create, model=project.model_used or DEFAULT_TEXT_MODEL,
        messages=[{"role": "system", "content": str(system_prompt)}, {"role": "user", "content": str(user_prompt)}],
        temperature=0.8, timeout=90.0, max_tokens=token_limit, seed=project_id
    )
    full_text = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
    if not full_text: raise ValueError("AI returned an empty story text.")

    await _update_project_state(project, progress=30, text=full_text)
    page_texts = _split_text_into_pages(full_text)
    await _delete_pages(project)
    await asyncio.gather(*[_create_page(project, i, text) for i, text in enumerate(page_texts, start=1)])
    await _save_event(project, "stage1_done", {"pages_created": len(page_texts)})

async def generate_metadata_and_cover_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage2_start", {})
    await _send(project_id, {"progress": 40, "message": str(_("Summarizing and drawing the cover..."))})
    
    metadata = await _generate_synopsis_and_tags_async(project.text)
    image_metadata = await _generate_cover_image_async(metadata, project)
    
    await _update_project_state(project, progress=65, **metadata, **image_metadata)
    await _save_event(project, "stage2_done", {})

async def generate_audio_logic(project_id: int):
    project = await _reload_project(project_id)
    if not project or project.status != 'running': return

    await _save_event(project, "stage3_start", {})
    await _send(project_id, {"progress": 70, "message": str(_("Recording narration for each page..."))})

    page_objects = await sync_to_async(list)(project.pages.all())
    
    semaphore = asyncio.Semaphore(3)
    async def generate_with_semaphore(page, project):
        async with semaphore:
            await asyncio.sleep(1)
            return await _generate_audio_for_page(page, project)
    audio_tasks = [generate_with_semaphore(page, project) for page in page_objects]
    
    audio_chunks = await asyncio.gather(*audio_tasks)

    await _send(project_id, {"progress": 90, "message": str(_("Combining narration..."))})
    combined_audio = None
    for chunk_io in audio_chunks:
        if chunk_io:
            try:
                chunk_audio = AudioSegment.from_file(chunk_io, format="mp3")
                combined_audio = chunk_audio if combined_audio is None else combined_audio + chunk_audio
            except Exception as e:
                logger.error(f"Failed to process audio chunk for project {project_id}: {e}")

    if combined_audio is None: raise RuntimeError("Failed to generate any valid audio chunks.")

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
    await _send(project_id, {"status": "done", "progress": 100, "message": str(_("Your story is complete!"))})

async def handle_generation_failure(project_id: int, exc: Exception):
    project = await _reload_project(project_id)
    if not project: return

    error_message = ""
    error_type = type(exc).__name__

    if isinstance(exc, RateLimitError):
        error_message = str(_("The AI story-making service is very busy. Please try again in a few moments."))
    elif isinstance(exc, APIError):
        error_message = str(_("A problem occurred with the AI service. This is likely temporary, please try again."))
    else:
        error_message = str(_("An unexpected error occurred while creating your story. Our team has been notified."))
        logger.error(f"UNHANDLED exception for Project {project_id}: {exc}", exc_info=True)

    await _update_project_state(project, status="failed", error=error_message, finished=True)
    await _save_event(project, "error", {"error": str(exc), "type": error_type})
    await _send(project_id, {"status": "failed", "error": error_message})
    await _cleanup_audio_chunks(project_id)