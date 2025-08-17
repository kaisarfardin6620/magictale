import asyncio
from typing import List
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import OpenAI

from .models import StoryProject, StoryPage, GenerationEvent

client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))

@sync_to_async
def _reload_project(project_id: int) -> StoryProject:
    return StoryProject.objects.select_related("onboarding","user").get(pk=project_id)

@sync_to_async
def _save_event(project: StoryProject, kind: str, payload: dict):
    GenerationEvent.objects.create(project=project, kind=kind, payload=payload)

@sync_to_async
def _update_progress(project: StoryProject, status: str = None, progress: int = None, error: str = None, finished=False):
    changed = []
    if status:
        project.status = status; changed.append("status")
    if progress is not None:
        project.progress = max(0, min(100, progress)); changed.append("progress")
    if error is not None:
        project.error = error; changed.append("error")
    if finished:
        project.finished_at = timezone.now(); changed.append("finished_at")
    if changed:
        project.save(update_fields=changed)
    return project.progress, project.status

@sync_to_async
def _persist_pages(project: StoryProject, pages: List[str]):
    StoryPage.objects.filter(project=project).delete()
    for i, text in enumerate(pages, start=1):
        StoryPage.objects.create(project=project, index=i, text=text)

async def _send(project_id: int, event: dict):
    layer = get_channel_layer()
    await layer.group_send(f"story_{project_id}", {"type": "progress", "event": event})

def _build_prompt(project: StoryProject) -> str:
    ob = project.onboarding
    child_name = getattr(ob, "child_name", "Emma")
    age = getattr(ob, "age", 6)
    pronouns = getattr(ob, "pronouns", "she/her")
    fav_animal = getattr(ob, "favorite_animal", "cat")
    fav_color = getattr(ob, "favorite_color", "blue")
    theme = project.theme
    style = project.art_style
    length = project.length
    difficulty = project.difficulty
    language = project.language

    return f"""
You are a children's storyteller. Write a {length} {language} story for a {age}-year-old child named {child_name} ({pronouns}).
Theme: {theme}. Visual art style reference (for tone only): {style}.
Include the favorite animal ({fav_animal}) and color ({fav_color}) as fun motifs.
Reading difficulty target: {difficulty}/5 (simpler words for lower numbers).
Return the story as 8 short scenes separated with this exact delimiter line:

--- PAGE ---

Keep each page 2–5 short sentences.
"""

def _split_into_pages(text: str) -> List[str]:
    parts = [p.strip() for p in text.split("--- PAGE ---") if p.strip()]
    if len(parts) <= 1:
        words = text.split()
        chunk = 150
        parts = [" ".join(words[i:i+chunk]) for i in range(0, len(words), chunk)]
    return parts[:12]  


async def run_generation_async(project_id: int):
    project = await _reload_project(project_id)
    await _save_event(project, "start", {"status": project.status})
    await _send(project_id, {"status":"running","progress":project.progress})

    try:
        prompt = _build_prompt(project)
        await _save_event(project, "prompt", {"prompt": prompt})
        await _update_progress(project, progress=10)

        model_name = project.model_used or "gpt-4o-mini"
        await _send(project_id, {"message":"Contacting model...", "progress":15})
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,  
            messages=[{"role":"system","content":"You are a helpful story writer for children."},
                      {"role":"user","content":prompt}],
            temperature=0.9,
        )
        await _update_progress(project, progress=60)

        content = resp.choices[0].message.content if resp.choices else ""
        await _save_event(project, "model_result", {"length": len(content)})
        await _send(project_id, {"message":"Draft received from model.", "progress":65})

        pages = _split_into_pages(content)
        await _persist_pages(project, pages)
        await _save_event(project, "pages_built", {"count": len(pages)})
        await _update_progress(project, progress=90)
        await _send(project_id, {"message":f"{len(pages)} pages created.", "progress":90})

        await _update_progress(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status":"done","progress":100})
    except Exception as e:
        await _update_progress(project, status="failed", error=str(e))
        await _save_event(project, "error", {"error": str(e)})
        await _send(project_id, {"status":"failed","error":str(e)})