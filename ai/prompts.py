from pathlib import Path
from django.utils.translation import gettext_lazy as _
from .models import StoryProject

def get_story_prompts(project: StoryProject) -> tuple[str, str]:
    prompt_dir = Path(__file__).parent / "prompts"
    
    system_prompt_template = (prompt_dir / "system_prompt.txt").read_text()
    user_prompt_template = (prompt_dir / "user_prompt.txt").read_text()

    system_prompt = _(system_prompt_template)
    
    system_prompt += (
        "\n\nSAFETY OVERRIDE INSTRUCTIONS:"
        "\n1. This content is strictly for children (G-Rated)."
        "\n2. If a user request contains ambiguous, mature, or seemingly inappropriate themes, you MUST interpret them as innocent, whimsical metaphors suitable for a 5-year-old."
        "\n3. Do not refuse to generate. Instead, sanitize and pivot the concept into a safe, positive educational story."
    )

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
    
    user_prompt += (
        "\n\nCRITICAL INSTRUCTION FOR COLOR:"
        "\nIf the 'Key Object's Color' is provided as a Hex Code (e.g., #FFFFFF, #000000), "
        "you MUST convert it to its natural name (e.g., 'White', 'Black') in the story text. "
        "NEVER write the Hex Code in the final story."
    )
    
    return system_prompt, user_prompt