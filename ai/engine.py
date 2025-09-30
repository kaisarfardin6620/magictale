import asyncio
import os
import json
from pathlib import Path
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import OpenAI
from mutagen.mp3 import MP3

from .models import StoryProject, GenerationEvent

client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

@sync_to_async
def _reload_project(project_id: int) -> StoryProject | None:
    return StoryProject.objects.filter(pk=project_id).first()

@sync_to_async
def _save_event(project: StoryProject, kind: str, payload: dict):
    GenerationEvent.objects.create(project=project, kind=kind, payload=payload)

@sync_to_async
def _update_progress(project: StoryProject, status: str = None, progress: int = None, error: str = None, finished=False):
    changed = []
    if status:
        project.status = status
        changed.append("status")
    if progress is not None:
        project.progress = max(0, min(100, progress))
        changed.append("progress")
    if error is not None:
        project.error = error
        changed.append("error")
    if finished:
        project.finished_at = timezone.now()
        changed.append("finished_at")
    if changed:
        project.save(update_fields=changed)
    return project.progress, project.status

@sync_to_async
def _save_project_fields(project: StoryProject, fields: dict):
    for key, value in fields.items():
        setattr(project, key, value)
    project.save(update_fields=list(fields.keys()))

async def _send(project_id: int, event: dict):
    layer = get_channel_layer()
    await layer.group_send(f"story_{project_id}", {"type": "progress", "event": event})

def _build_story_prompt(project: StoryProject) -> str:
    story_subject = project.custom_prompt.strip() if project.custom_prompt and project.custom_prompt.strip() else f"Theme: {project.theme}"
    return f"""
You are a children's storyteller. Write a complete {project.length} {project.language} story for a {project.age}-year-old child named {project.child_name} ({project.pronouns}).
{story_subject}.
Include their favorite animal ({project.favorite_animal}) and favorite color ({project.favorite_color}) as fun motifs.
Reading difficulty target: {project.difficulty}/5.
Return the entire story as a single block of text with paragraphs separated by newlines.
"""

def _build_synopsis_prompt(story_text: str) -> str:
    return f"""
You are a story analyst. Based on the following children's story, perform two tasks:
1. Write a short, exciting one-paragraph synopsis (3-4 sentences).
2. Suggest 3 relevant, single-word tags (e.g., Adventure, Friendship, Forest, Magic).
Return your response in a JSON format like this:
{{
  "synopsis": "Your generated synopsis here.",
  "tags": "Tag1, Tag2, Tag3"
}}
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

async def run_generation_async(project_id: int):
    project = await _reload_project(project_id)
    if project is None: return

    await _save_event(project, "start", {"status": project.status})
    await _send(project_id, {"status": "running", "progress": 5})

    try:
        await _send(project_id, {"message": "Crafting your unique story...", "progress": 15})
        story_prompt = _build_story_prompt(project)
        text_resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=project.model_used or settings.AI_TEXT_MODEL,
            messages=[{"role": "user", "content": story_prompt}],
            temperature=0.9, timeout=90.0
        )
        full_text = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
        await _save_project_fields(project, {"text": full_text})
        await _update_progress(project, progress=30)

        await _send(project_id, {"message": "Summarizing the adventure...", "progress": 40})
        synopsis_prompt = _build_synopsis_prompt(full_text)
        synopsis_resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.AI_TEXT_MODEL,
            messages=[{"role": "user", "content": synopsis_prompt}],
            response_format={"type": "json_object"}, temperature=0.5
        )
        try:
            metadata = json.loads(synopsis_resp.choices[0].message.content)
            await _save_project_fields(project, metadata)
        except (json.JSONDecodeError, IndexError):
            metadata = {"synopsis": "A magical adventure awaits!"}
        await _update_progress(project, progress=50)

        await _send(project_id, {"message": "Creating the cover art...", "progress": 60})
        image_prompt = _build_cover_image_prompt(metadata.get("synopsis", project.theme), project)
        image_resp = await asyncio.to_thread(
            client.images.generate,
            model=settings.AI_IMAGE_MODEL,
            prompt=image_prompt, n=1, size="1024x1024", response_format="url", timeout=120.0
        )
        image_url = image_resp.data[0].url if image_resp.data else ""
        await _save_project_fields(project, {"image_url": image_url, "cover_image_url": image_url})
        await _update_progress(project, progress=80)

        await _send(project_id, {"message": "Recording the narration...", "progress": 90})
        audio_resp = await asyncio.to_thread(
            client.audio.speech.create,
            model=settings.AI_AUDIO_MODEL,
            voice=project.voice or "alloy",
            input=full_text, timeout=180.0
        )
        audio_dir = Path(settings.MEDIA_ROOT) / 'audio'
        os.makedirs(audio_dir, exist_ok=True)
        file_path = audio_dir / f"story_{project.id}.mp3"
        audio_resp.stream_to_file(file_path)
        audio_url = f"{settings.MEDIA_URL}audio/story_{project.id}.mp3"
        
        duration_seconds = 0
        try:
            audio_file = MP3(file_path)
            duration_seconds = int(audio_file.info.length)
        except Exception as e:
            print(f"Could not read audio duration for project {project.id}: {e}")
        
        await _save_project_fields(project, {
            "audio_url": audio_url,
            "audio_duration_seconds": duration_seconds
        })

        await _update_progress(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status": "done", "progress": 100, "message": "Your story is complete!"})

    except Exception as e:
        error_message = str(e)
        await _update_progress(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": error_message})
        await _send(project_id, {"status": "failed", "error": "Something went wrong during generation."})