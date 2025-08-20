# ai/engine.py

import asyncio
import os
import json
from pathlib import Path
from typing import List, Dict
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import OpenAI

from .models import StoryProject, StoryPage, GenerationEvent

# Initialize the OpenAI client
client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

# --- Database & Channel Helpers (Async) ---

@sync_to_async
def _reload_project(project_id: int) -> StoryProject:
    """Fetches the project and related user/onboarding data from the database."""
    return StoryProject.objects.select_related("user").get(pk=project_id)

@sync_to_async
def _save_event(project: StoryProject, kind: str, payload: dict):
    """Saves a generation event log to the database."""
    GenerationEvent.objects.create(project=project, kind=kind, payload=payload)

@sync_to_async
def _update_progress(project: StoryProject, status: str = None, progress: int = None, error: str = None, finished=False):
    """Updates the project's status and progress in the database."""
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
def _persist_pages(project: StoryProject, pages_text: List[str]):
    """Deletes old pages and creates new ones for the project."""
    StoryPage.objects.filter(project=project).delete()
    new_pages = [StoryPage(project=project, index=i, text=text) for i, text in enumerate(pages_text, start=1)]
    StoryPage.objects.bulk_create(new_pages)

@sync_to_async
def _save_project_fields(project: StoryProject, fields: Dict):
    """Saves arbitrary fields to the project instance."""
    for key, value in fields.items():
        setattr(project, key, value)
    project.save(update_fields=list(fields.keys()))

async def _send(project_id: int, event: dict):
    """Sends a progress update over the WebSocket."""
    layer = get_channel_layer()
    await layer.group_send(f"story_{project_id}", {"type": "progress", "event": event})


# --- AI Prompt Builders ---

def _build_story_prompt(project: StoryProject) -> str:
    """Builds the main text prompt for the story."""
    story_subject = project.custom_prompt.strip() if project.custom_prompt and project.custom_prompt.strip() else f"Theme: {project.theme}"

    return f"""
You are a children's storyteller. Write a {project.length} {project.language} story for a {project.age}-year-old child named {project.child_name} ({project.pronouns}).
{story_subject}.
Visual art style reference (for tone only): {project.art_style}.
Include their favorite animal ({project.favorite_animal}) and favorite color ({project.favorite_color}) as fun motifs in the story.
Reading difficulty target: {project.difficulty}/5 (use simpler words and sentence structures for lower numbers).
Return the story as 8 short scenes separated with this exact delimiter line:

--- PAGE ---

Keep each page to 2-5 short sentences. Do not write the page numbers.
"""

def _build_synopsis_prompt(story_text: str) -> str:
    """Builds the prompt to generate a synopsis and tags from the full story."""
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

def _build_image_prompt(page_text: str, project: StoryProject) -> str:
    """Builds a DALL-E prompt for a single story page."""
    return f"""
A beautiful children's book illustration in the art style of {project.art_style}.
The scene is about: "{page_text}"
The illustration should be vibrant, whimsical, and suitable for a young child.
Do not include any text, letters, words, or bubbles in the image.
"""

# --- AI Generation & File Handling Helpers ---

def _split_into_pages(text: str) -> List[str]:
    """Splits the AI's text output into a list of pages."""
    parts = [p.strip() for p in text.split("--- PAGE ---") if p.strip()]
    return parts[:12] # Limit to a maximum of 12 pages

@sync_to_async
def _generate_and_save_image(page: StoryPage, project: StoryProject):
    """Generates an image for a page and saves the URL."""
    prompt = _build_image_prompt(page.text, project)
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="url",
            timeout=120.0,
        )
        page.image_url = response.data[0].url
        page.save(update_fields=["image_url"])
    except Exception as e:
        print(f"Image generation failed for project {project.id}, page {page.index}: {e}")
        raise e

@sync_to_async
def _generate_and_save_audio(page: StoryPage, project: StoryProject):
    """Generates audio for a page and saves the file."""
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=project.voice or "alloy",
            input=page.text,
            timeout=60.0,
        )
        audio_dir = Path(settings.MEDIA_ROOT) / 'audio'
        os.makedirs(audio_dir, exist_ok=True)
        file_path = audio_dir / f"{page.id}.mp3"
        response.stream_to_file(file_path)
        page.audio_url = f"{settings.MEDIA_URL}audio/{page.id}.mp3"
        page.save(update_fields=["audio_url"])
    except Exception as e:
        print(f"Audio generation failed for project {project.id}, page {page.index}: {e}")
        raise e

# --- Main Asynchronous Generation Task ---

async def run_generation_async(project_id: int):
    """The main async task that orchestrates the entire story generation process."""
    project = await _reload_project(project_id)
    await _save_event(project, "start", {"status": project.status})
    await _send(project_id, {"status": "running", "progress": project.progress})

    try:
        # 1. Generate Story Text
        prompt = _build_story_prompt(project)
        await _save_event(project, "prompt", {"prompt": prompt})
        await _update_progress(project, progress=10)
        await _send(project_id, {"message": "Crafting your unique story...", "progress": 15})

        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=project.model_used or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful and creative storyteller for children."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            timeout=90.0,
        )
        await _update_progress(project, progress=50)

        content = resp.choices[0].message.content if resp.choices else ""
        await _save_event(project, "model_result", {"length": len(content)})
        await _send(project_id, {"message": "Story draft received!", "progress": 55})

        pages_text = _split_into_pages(content)
        await _persist_pages(project, pages_text)
        await _save_event(project, "pages_built", {"count": len(pages_text)})
        await _update_progress(project, progress=60)

        # 2. Generate Images and Audio Concurrently
        await _send(project_id, {"message": f"Creating {len(pages_text)} pages of art and audio...", "progress": 65})
        project_pages = await sync_to_async(list)(project.pages.all())
        multimedia_tasks = []
        for page in project_pages:
            multimedia_tasks.append(_generate_and_save_image(page, project))
            multimedia_tasks.append(_generate_and_save_audio(page, project))
        await asyncio.gather(*multimedia_tasks)
        await _save_event(project, "multimedia_done", {})
        await _update_progress(project, progress=90)
        
        # 3. Generate Synopsis, Tags, and Save Cover Image
        await _send(project_id, {"message": "Adding the finishing touches...", "progress": 91})
        synopsis_prompt = _build_synopsis_prompt(content)
        synopsis_resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": synopsis_prompt}],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        
        try:
            extra_data = json.loads(synopsis_resp.choices[0].message.content)
        except (json.JSONDecodeError, IndexError, TypeError):
            extra_data = {"synopsis": "A magical adventure awaits!", "tags": "Magic"}

        first_page = await sync_to_async(project.pages.order_by('index').first)()
        cover_image_url = first_page.image_url if first_page else ""
        extra_data['cover_image_url'] = cover_image_url
        
        await _save_project_fields(project, extra_data)
        await _save_event(project, "metadata_generated", extra_data)
        await _update_progress(project, progress=95)

        # 4. Finalize
        await _update_progress(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status": "done", "progress": 100, "message": "Your story is complete!"})

    except Exception as e:
        print(f"An error occurred during generation for project {project.id}: {e}")
        error_message = str(e)
        await _update_progress(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": error_message})
        await _send(project_id, {"status": "failed", "error": "Something went wrong during generation."})