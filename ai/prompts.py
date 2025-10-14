from pathlib import Path
from django.utils.translation import gettext_lazy as _
from .models import StoryProject

def get_story_prompts(project: StoryProject) -> tuple[str, str]:
    prompt_dir = Path(__file__).parent / "prompts"
    
    system_prompt_template = (prompt_dir / "system_prompt.txt").read_text()
    user_prompt_template = (prompt_dir / "user_prompt.txt").read_text()

    system_prompt = _(system_prompt_template)
    
    safe_custom_prompt = project.custom_prompt.strip()
    if safe_custom_prompt:
        story_subject = f"A custom story based on this user request: <user_request>{safe_custom_prompt}</user_request>"
    else:
        story_subject = f"A story about the theme: {project.theme}"
    user_prompt = _(user_prompt_template).format(
        length=project.length,
        language=project.language,
        child_name=project.child_name,
        pronouns=project.pronouns,
        age=project.age,
        story_subject=story_subject,
        favorite_animal=project.favorite_animal,
        favorite_color=project.favorite_color,
        difficulty=project.difficulty
    )
    
    return system_prompt, user_prompt