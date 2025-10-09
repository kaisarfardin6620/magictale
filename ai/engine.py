import asyncio
import os
import json
import io
from pathlib import Path
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import OpenAI
from mutagen.mp3 import MP3
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pydub import AudioSegment
from django.utils.translation import gettext_lazy as _

from .models import StoryProject, GenerationEvent, StoryPage

client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

LENGTH_TO_TOKENS = {
    "short": 2000, "medium": 3000, "long": 5000,
}

@sync_to_async
def _reload_project(project_id: int) -> StoryProject | None:
    return StoryProject.objects.prefetch_related('pages').filter(pk=project_id).first()

@sync_to_async
def _save_event(project: StoryProject, kind: str, payload: dict):
    GenerationEvent.objects.create(project=project, kind=kind, payload=payload)

@sync_to_async
def _update_progress(project: StoryProject, status: str = None, progress: int = None, error: str = None, finished=False):
    changed = []
    if status: project.status = status; changed.append("status")
    if progress is not None: project.progress = max(0, min(100, progress)); changed.append("progress")
    if error is not None: project.error = error; changed.append("error")
    if finished: project.finished_at = timezone.now(); changed.append("finished_at")
    if changed: project.save(update_fields=changed)
    return project.progress, project.status

@sync_to_async
def _save_project_fields(project: StoryProject, fields: dict):
    for key, value in fields.items():
        setattr(project, key, value)
    project.save(update_fields=list(fields.keys()))

async def _send(project_id: int, event: dict):
    layer = get_channel_layer()
    await layer.group_send(f"story_{project_id}", {"type": "progress", "event": event})

def _split_text_into_pages(full_text: str):
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
    pages = []
    for i in range(0, len(paragraphs), 3):
        page_content = "\n\n".join(paragraphs[i:i+3]) 
        pages.append(page_content)
    return pages

def _build_synopsis_prompt(story_text: str) -> str:
    return f"""
You are a story analyst. Based on the following children's story, perform two tasks:
1. Write a short, exciting one-paragraph synopsis (3-4 sentences).
2. Suggest 3 relevant, single-word tags (e.g., Adventure, Friendship, Forest, Magic).
Return your response in a JSON format like this: {{ "synopsis": "Your synopsis here.", "tags": "Tag1, Tag2, Tag3" }}
Here is the story:
---
{story_text}
---
"""

def _build_cover_image_prompt(synopsis: str, project: StoryProject) -> str:
    return f"""
A beautiful children's book cover illustration in the art style of {project.art_style}.
The story is about: "{synopsis}"
The illustration should be vibrant, whimsical, and suitable for a young child, worthy of a book cover.
Do not include any text, letters, words, or bubbles in the image.
"""

async def _generate_audio_for_page(page: StoryPage, project: StoryProject):
    """
    An individual, awaitable task to generate audio for a single page.
    """
    try:
        audio_resp_chunk = await asyncio.to_thread(
            client.audio.speech.create, model=settings.AI_AUDIO_MODEL,
            voice=project.voice or "alloy", input=page.text, timeout=60.0
        )
        audio_content = audio_resp_chunk.content
        
        chunk_file_path = f"audio/chunks/story_{project.id}_page_{page.index}.mp3"
        saved_chunk_path = await sync_to_async(default_storage.save)(chunk_file_path, ContentFile(audio_content))
        page.audio_url = await sync_to_async(default_storage.url)(saved_chunk_path)
        await sync_to_async(page.save)()
        
        return io.BytesIO(audio_content)
    except Exception as e:
        print(f"Failed to generate audio for page {page.index}: {e}")
        return None

async def run_generation_async(project_id: int):
    project = await _reload_project(project_id)
    if project is None: return

    await _save_event(project, "start", {"status": project.status})
    await _send(project_id, {"status": "running", "progress": 5})

    try:
        system_prompt = _("You are \"MagicTale,\" a world-renowned children's storyteller. Your voice is gentle, warm, and full of wonder. You must always be positive, encouraging, and kind in your narration. Your rules are: - Use simple, age-appropriate language. - Keep sentences clear and short. - Weave in themes of friendship, courage, and kindness. - Avoid scary or negative themes. - Write the story as a single, continuous narrative.")
        story_subject = project.custom_prompt.strip() or _("A story about: {theme}").format(theme=project.theme)
        user_prompt = _("Please write a complete {length} story using these details:\n- Language: {language}\n- Child's Name: {child_name}\n- Child's Pronouns: {pronouns}\n- Child's Age: {age}\n- Story Details: {story_subject}\n- Favorite Animal to include: {favorite_animal}\n- Favorite Color to include: {favorite_color}\n- Reading Difficulty Target: {difficulty}/5").format(
            length=project.length, language=project.language, child_name=project.child_name,
            pronouns=project.pronouns, age=project.age, story_subject=story_subject,
            favorite_animal=project.favorite_animal, favorite_color=project.favorite_color,
            difficulty=project.difficulty
        )
        await _send(project_id, {"message": _("Whispering to the story spirits..."), "progress": 15})
        token_limit = LENGTH_TO_TOKENS.get(project.length, 2000)
        
        text_resp = await asyncio.to_thread(
            client.chat.completions.create, model=project.model_used or settings.AI_TEXT_MODEL,
            messages=[{"role": "system", "content": str(system_prompt)}, {"role": "user", "content": str(user_prompt)}],
            temperature=0.8, timeout=90.0, max_tokens=token_limit
        )
        full_text = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
        await _save_project_fields(project, {"text": full_text})
        await _update_progress(project, progress=30)

        page_texts = _split_text_into_pages(full_text)
        page_objects = []
        await sync_to_async(project.pages.all().delete)()
        for i, page_text in enumerate(page_texts, start=1):
            page = await sync_to_async(StoryPage.objects.create)(project=project, index=i, text=page_text)
            page_objects.append(page)
        await _save_event(project, "pages_created", {"count": len(page_objects)})
        
        await _send(project_id, {"message": _("Summarizing the adventure..."), "progress": 40})
        synopsis_prompt = _build_synopsis_prompt(full_text)
        synopsis_resp = await asyncio.to_thread(
            client.chat.completions.create, model=settings.AI_TEXT_MODEL,
            messages=[{"role": "user", "content": synopsis_prompt}],
            response_format={"type": "json_object"}, temperature=0.5
        )
        try:
            metadata = json.loads(synopsis_resp.choices[0].message.content)
            if not metadata.get("synopsis") or len(metadata.get("synopsis", "")) < 20:
                metadata["synopsis"] = _("A wonderful and magical adventure.")
            await _save_project_fields(project, metadata)
        except (json.JSONDecodeError, IndexError):
            metadata = {"synopsis": _("A magical adventure awaits!")}
        await _update_progress(project, progress=50)

        await _send(project_id, {"message": _("Creating the cover art..."), "progress": 60})
        image_prompt = _build_cover_image_prompt(metadata.get("synopsis", project.theme), project)
        image_resp = await asyncio.to_thread(
            client.images.generate, model=settings.AI_IMAGE_MODEL,
            prompt=image_prompt, n=1, size="1024x1024", response_format="url", timeout=120.0
        )
        image_url = image_resp.data[0].url if image_resp.data else ""
        await _save_project_fields(project, {"image_url": image_url, "cover_image_url": image_url})
        await _update_progress(project, progress=80)
        
        await _send(project_id, {"message": _("Recording narration for each page..."), "progress": 85})
        audio_tasks = [_generate_audio_for_page(page, project) for page in page_objects]
        audio_chunks = await asyncio.gather(*audio_tasks)

        await _send(project_id, {"message": _("Combining narration..."), "progress": 95})
        combined_audio = AudioSegment.empty()
        for chunk_io in audio_chunks:
            if chunk_io:
                chunk_io.seek(0)
                combined_audio += AudioSegment.from_mp3(chunk_io)

        final_audio_io = io.BytesIO()
        combined_audio.export(final_audio_io, format="mp3")
        final_audio_io.seek(0)
        
        final_file_path = f"audio/story_{project.id}_full.mp3"
        saved_final_path = await sync_to_async(default_storage.save)(final_file_path, ContentFile(final_audio_io.read()))
        final_audio_url = await sync_to_async(default_storage.url)(saved_final_path)

        duration_seconds = int(combined_audio.duration_seconds)
        
        await _save_project_fields(project, {
            "audio_url": final_audio_url,
            "audio_duration_seconds": duration_seconds
        })

        await _update_progress(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status": "done", "progress": 100, "message": _("Your story is complete!")})

    except Exception as e:
        error_message = str(e)
        await _update_progress(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": error_message})
        await _send(project_id, {"status": "failed", "error": _("Something went wrong during generation.")})