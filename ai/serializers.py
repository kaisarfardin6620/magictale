from rest_framework import serializers
from .models import StoryProject
from authentication.models import OnboardingStatus
from django.conf import settings

class HeroSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingStatus
        fields = ["child_name", "age", "pronouns", "favorite_animal", "favorite_color"]

class StoryProjectCreateSerializer(serializers.ModelSerializer):
    hero = HeroSerializer(write_only=True)
    class Meta:
        model = StoryProject
        fields = [
            "id", "hero", "theme", "custom_prompt", "art_style", "language",
            "voice", "length", "difficulty", "model_used"
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        user = self.context["request"].user
        hero_data = validated_data.pop('hero')
        onboarding_profile, _ = OnboardingStatus.objects.get_or_create(user=user)
        for attr, value in hero_data.items():
            setattr(onboarding_profile, attr, value)
        onboarding_profile.save()
        story_project = StoryProject.objects.create(
            user=user, onboarding=onboarding_profile,
            child_name=hero_data['child_name'], age=hero_data['age'],
            pronouns=hero_data['pronouns'], favorite_animal=hero_data['favorite_animal'],
            favorite_color=hero_data['favorite_color'], **validated_data
        )
        return story_project

class StoryProjectDetailSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    class Meta:
        model = StoryProject
        depth = 0
        fields = [
            "id", "user", "onboarding", "is_saved",
            "child_name", "age", "pronouns", "favorite_animal", "favorite_color",
            "theme", "custom_prompt", "art_style", "language", "voice",
            "length", "difficulty", "model_used", "synopsis", "tags",
            "status", "progress", "error", "read_count", "likes_count", "shares_count",
            "created_at", "started_at", "finished_at",
            "text", "image_url", "audio_url"
        ]
        
    def get_image_url(self, obj):
        return obj.image_url if obj.image_url else None

    def get_audio_url(self, obj):
        if obj.audio_url:
            if settings.USE_S3_STORAGE:
                return obj.audio_url
            return f"{settings.BACKEND_BASE_URL}{obj.audio_url}"
        return None