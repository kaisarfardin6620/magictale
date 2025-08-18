# ai/serializers.py

from rest_framework import serializers
from .models import StoryProject, StoryPage

class StoryPageSerializer(serializers.ModelSerializer):
    """
    Serializer for a single page of a story, including text and generated content URLs.
    """
    class Meta:
        model = StoryPage
        fields = ["id", "index", "text", "image_url", "audio_url"]

class StoryProjectCreateSerializer(serializers.ModelSerializer):
    """
    Serializer used for creating a new story project. It only includes the
    fields required to start the generation process.
    """
    class Meta:
        model = StoryProject
        # === FIX: Added 'custom_prompt' to the list of fields ===
        fields = [
            "id", "onboarding", "theme", "custom_prompt", "art_style", "language",
            "voice", "length", "difficulty", "model_used"
        ]
        # Make the 'id' field read-only, as it's assigned on creation
        read_only_fields = ["id"]

    def create(self, validated_data):
        """
        Override the create method to automatically assign the logged-in user
        to the new story project.
        """
        user = self.context["request"].user
        return StoryProject.objects.create(user=user, **validated_data)

class StoryProjectDetailSerializer(serializers.ModelSerializer):
    """
    A detailed serializer for a story project, which includes all its pages.
    This is used for retrieving a single project or listing all projects.
    """
    # Nest the page serializer to include all pages in the project detail view
    pages = StoryPageSerializer(many=True, read_only=True)

    class Meta:
        model = StoryProject
        fields = [
            "id", "user", "onboarding", "theme", "custom_prompt", "art_style", "language", "voice",
            "length", "difficulty", "model_used", "status", "progress", "error",
            "created_at", "started_at", "finished_at", "pages"
        ]
        # These fields are set by the server/engine, not by the user directly
        read_only_fields = (
            "id", "user", "status", "progress", "error", "created_at", 
            "started_at", "finished_at", "pages"
        )