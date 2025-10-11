import asyncio
import os
import json
import io
from pathlib import Path
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from openai import OpenAI, RateLimitError, APIError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pydub import AudioSegment
from django.utils.translation import gettext_lazy as _
import logging
import tempfile
from .models import StoryProject, GenerationEvent, StoryPage

client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))
logger = logging.getLogger(__name__)

LENGTH_TO_TOKENS = {
    "short": 4000, "medium": 7000, "long": 10000, 
}
DEFAULT_TEXT_MODEL = getattr(settings, "AI_TEXT_MODEL", "gpt-4-turbo")

async def api_with_retry(func, *args, max_retries=3, **kwargs):
    """Wraps synchronous API calls with exponential backoff and retries."""
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
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
        page_content = "\n\n".join(paragraphs[i:i+3]) 
        pages.append(page_content)
        
    return pages

def _generate_synopsis_and_tags_sync(full_text: str):
    """Generates synopsis and tags using LLM (synchronous helper)."""
    synopsis_prompt = _build_synopsis_prompt(full_text)
    
    synopsis_resp = client.chat.completions.create(
        model=DEFAULT_TEXT_MODEL, 
        messages=[{"role": "user", "content": synopsis_prompt}],
        response_format={"type": "json_object"}, 
        temperature=0.5,
        timeout=30.0
    )
    
    metadata = {}
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
def _generate_cover_image_sync(metadata: dict, project: StoryProject):
    """Generates the cover image using DALL-E (synchronous helper)."""
    image_prompt = _build_cover_image_prompt(metadata.get("synopsis", project.theme), project)
    
    image_resp = client.images.generate(
        model=settings.AI_IMAGE_MODEL,
        prompt=image_prompt, n=1, size="1024x1024", 
        response_format="url", timeout=120.0
    )
    
    image_url = image_resp.data[0].url if image_resp.data else ""
    return {"image_url": image_url, "cover_image_url": image_url}


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
    prompt_subject = synopsis if synopsis and len(synopsis) > 20 else project.theme
    return f"""
A beautiful children's book cover illustration in the art style of {project.art_style}.
The story is about: "{prompt_subject}"
The illustration should be vibrant, whimsical, and suitable for a young child, worthy of a book cover.
Do not include any text, letters, words, or bubbles in the image.
"""

async def _generate_audio_for_page(page: StoryPage, project: StoryProject):
    """Generates audio for a single page with retry logic."""
    try:
        audio_resp_chunk = await api_with_retry(
            client.audio.speech.create, 
            model=settings.AI_AUDIO_MODEL,
            voice=project.voice or "alloy", 
            input=page.text, 
            timeout=60.0
        )
        audio_content = audio_resp_chunk.content
        
        chunk_file_path = f"audio/chunks/story_{project.id}_page_{page.index}.mp3"
        saved_chunk_path = await sync_to_async(default_storage.save)(chunk_file_path, ContentFile(audio_content))
        page.audio_url = await sync_to_async(default_storage.url)(saved_chunk_path)
        await sync_to_async(page.save)()
        
        return io.BytesIO(audio_content)
    except Exception as e:
        logger.error(f"Failed to generate audio for page {page.index} (Project {project.id}): {e}")
        return None

async def _cleanup_audio_chunks(project_id: int):
    """Clean up temporary audio chunk files from storage"""
    try:
        @sync_to_async
        def delete_chunks():
            from django.core.files.storage import default_storage
            if hasattr(default_storage, 'listdir'):
                try:
                    dirs, files = default_storage.listdir('audio/chunks')
                except Exception:
                    return 
                    
                for filename in files:
                    if f"story_{project_id}_page_" in filename:
                        default_storage.delete(Path('audio/chunks') / filename)
            
        await delete_chunks()
        logger.info(f"Cleaned up audio chunks for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to clean up audio chunks for project {project_id}: {e}")

async def run_generation_async(project_id: int):
    project = await _reload_project(project_id)
    if project is None: return

    try:
        await _save_event(project, "start", {"status": project.status})
        await _send(project_id, {"status": "running", "progress": 5})

        system_prompt = _("""
You are "MagicTale," a master children's storyteller. Your goal is to write a unique, captivating story for a young child.
Your voice must be gentle, enchanting, and full of wonder. You must be relentlessly positive, encouraging, and kind.
RULES FOR NARRATION:
1. **Pacing & Flow:** Maintain a slow, consistent, and rhythmic pace suitable for reading aloud.
2. **Vocabulary:** Use only simple, age-appropriate, and imaginative language. Avoid complex concepts or jargon.
3. **Themes:** Weave in core, positive moral themes: **courage, kindness, and friendship**.
4. **Safety:** Absolutely **avoid** scary situations, negativity, conflict that causes sadness, or anything that could be frightening. Every challenge must be solved with a gentle, clever solution.
5. **Structure:** Write the story as a single, continuous narrative with a clear beginning, middle (2-3 main friendly events/challenges), and a happy ending. Conclude with a clear, simple one-sentence takeaway about the virtue demonstrated (e.g., 'And that's how Leo learned the power of kindness!').
""")
        
        story_subject = project.custom_prompt.strip() or _("A story about: {theme}").format(theme=project.theme)
        
        user_prompt = _("""
Please write a complete {length} story using these details:
- **Language:** {language}
- **Hero's Name:** {child_name}
- **Hero's Pronouns:** {pronouns}
- **Hero's Age:** {age} (Keep the story simple enough for this age).
- **Core Subject:** {story_subject}
- **Key Companion/Item:** The hero's main companion or magical item must be a **{favorite_animal}** or **{favorite_animal}**-themed (e.g., a lion plush, a cat-shaped ship).
- **Key Object's Color:** A special object in the story (e.g., a magical gem, a map, a flag) must be the color **{favorite_color}**.
- **Reading Difficulty Target:** {difficulty}/5 (Simpler is better).

**IMPORTANT LENGTH INSTRUCTION (FOR LONG STORIES):**
Since this is a '{length}' story, you must include a rich level of detail. The adventure must have **at least five distinct, descriptive scenes** and **use extensive dialogue and detailed sensory descriptions** to fill the narrative space and make the journey feel grand. Do not conclude until the story is fully elaborated.
""").format(
            length=project.length, language=project.language, child_name=project.child_name,
            pronouns=project.pronouns, age=project.age, story_subject=story_subject,
            favorite_animal=project.favorite_animal, favorite_color=project.favorite_color,
            difficulty=project.difficulty
        )
        await _send(project_id, {"message": _("Whispering to the story spirits..."), "progress": 15})
        token_limit = LENGTH_TO_TOKENS.get(project.length, 2000)
        
        text_resp = await api_with_retry(
            client.chat.completions.create, 
            model=project.model_used or DEFAULT_TEXT_MODEL,
            messages=[{"role": "system", "content": str(system_prompt)}, {"role": "user", "content": str(user_prompt)}],
            temperature=0.8, 
            timeout=90.0, 
            max_tokens=token_limit,
            seed=project_id 
        )
        
        full_text = text_resp.choices[0].message.content.strip() if text_resp.choices else ""
        if not full_text:
            raise ValueError("AI returned an empty story text.")
            
        await _update_project_state(project, progress=30, text=full_text)
        
        page_texts = _split_text_into_pages(full_text)
        await _delete_pages(project)
        
        page_objects = [
            await _create_page(project, i, page_text)
            for i, page_text in enumerate(page_texts, start=1)
        ]
        await _save_event(project, "pages_created", {"count": len(page_objects)})
        
        await _send(project_id, {"message": _("Summarizing and drawing the cover..."), "progress": 40})

        synopsis_task = await api_with_retry(_generate_synopsis_and_tags_sync, full_text)
        metadata = synopsis_task
        
        image_task = await api_with_retry(_generate_cover_image_sync, metadata, project)
        image_metadata = image_task
        
        await _update_project_state(project, progress=65, **metadata, **image_metadata)
        
        await _send(project_id, {"message": _("Recording narration for each page..."), "progress": 80})
        audio_tasks = [_generate_audio_for_page(page, project) for page in page_objects]
        audio_chunks = await asyncio.gather(*audio_tasks)

        await _send(project_id, {"message": _("Combining narration..."), "progress": 90})
        
        combined_audio = None
        
        for chunk_io in audio_chunks:
            if chunk_io:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_chunk:
                    temp_chunk.write(chunk_io.getvalue())
                    temp_chunk.flush()
                    
                    try:
                        chunk_audio = AudioSegment.from_file(temp_chunk.name, format="mp3")
                        if combined_audio is None:
                            combined_audio = chunk_audio
                        else:
                            combined_audio += chunk_audio
                    except Exception as e:
                        logger.error(f"Failed to process chunk audio: {e}")
                    
                    os.unlink(temp_chunk.name)
        
        if combined_audio is None:
            raise RuntimeError("Failed to generate any audio chunks.")

        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_combined:
            combined_audio.export(temp_combined.name, format="mp3")
            
            with open(temp_combined.name, 'rb') as f:
                final_audio_content = f.read()
        
        os.unlink(temp_combined.name) 
        
        final_file_path = f"audio/story_{project.id}_full.mp3"
        saved_final_path = await sync_to_async(default_storage.save)(final_file_path, ContentFile(final_audio_content))
        final_audio_url = await sync_to_async(default_storage.url)(saved_final_path)

        duration_seconds = int(combined_audio.duration_seconds)
        
        await _update_project_state(project, 
            audio_url=final_audio_url,
            audio_duration_seconds=duration_seconds
        )

        await _update_project_state(project, status="done", progress=100, finished=True)
        await _save_event(project, "done", {})
        await _send(project_id, {"status": "done", "progress": 100, "message": _("Your story is complete!")})


    except RateLimitError as e:
        error_message = _("The AI story-making service is very busy right now. Please try again in a few moments.")
        logger.warning(f"Rate limit hit for Project {project_id}: {e}", exc_info=True)
        await _update_project_state(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": str(e), "type": "RateLimitError"})
        await _send(project_id, {"status": "failed", "error": error_message})

    except APIError as e:
        error_message = _("There was a problem talking to the AI. This is likely a temporary issue, please try again.")
        logger.error(f"OpenAI API Error for Project {project_id}: {e}", exc_info=True)
        await _update_project_state(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": str(e), "type": "APIError"})
        await _send(project_id, {"status": "failed", "error": error_message})

    except (ValueError, RuntimeError) as e:
        error_message = _(f"An internal error occurred while building the story: {e}")
        logger.error(f"Data or runtime error during generation for Project {project_id}: {e}", exc_info=True)
        await _update_project_state(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": str(e), "type": "InternalGenerationError"})
        await _send(project_id, {"status": "failed", "error": error_message})

    except Exception as e:
        error_message = _("An unexpected error occurred while creating your story. Our team has been notified.")
        logger.error(f"UNHANDLED exception during generation for Project {project_id}: {e}", exc_info=True)
        await _update_project_state(project, status="failed", error=error_message)
        await _save_event(project, "error", {"error": str(e), "type": "GenericException"})
        await _send(project_id, {"status": "failed", "error": error_message})
    
    finally:
        await _cleanup_audio_chunks(project.id)