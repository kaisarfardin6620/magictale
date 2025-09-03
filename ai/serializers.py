# ai/serializers.py

from rest_framework import serializers
from .models import StoryProject, StoryPage, GalleryStory
from authentication.models import OnboardingStatus

class StoryPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryPage
        fields = ["id", "index", "text", "image_url", "audio_url"]

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

    def validate(self, data):
        """
        Enforce subscription limits: only 'master' plan or trial users
        can create 'long' stories.
        """
        if data.get("length") == "long":
            user = self.context["request"].user
            subscription = getattr(user, 'subscription', None)

            if not subscription:
                raise serializers.ValidationError({"length": "A subscription is required to create long stories."})

            is_master_plan = subscription.plan == 'master'
            is_trialing = subscription.status == 'trialing'

            if not (is_trialing or is_master_plan):
                raise serializers.ValidationError({"length": "You must upgrade to the Story Master plan to create long stories."})

        return data

    def create(self, validated_data):
        user = self.context["request"].user
        hero_data = validated_data.pop('hero')

        onboarding_profile, _ = OnboardingStatus.objects.get_or_create(user=user)
        for attr, value in hero_data.items():
            setattr(onboarding_profile, attr, value)
        onboarding_profile.save()

        story_project = StoryProject.objects.create(
            user=user,
            onboarding=onboarding_profile,
            child_name=hero_data['child_name'],
            age=hero_data['age'],
            pronouns=hero_data['pronouns'],
            favorite_animal=hero_data['favorite_animal'],
            favorite_color=hero_data['favorite_color'],
            **validated_data
        )
        return story_project

class StoryProjectDetailSerializer(serializers.ModelSerializer):
    pages = StoryPageSerializer(many=True, read_only=True)

    class Meta:
        model = StoryProject
        fields = [
            "id", "user", "onboarding", "is_saved",
            "child_name", "age", "pronouns", "favorite_animal", "favorite_color",
            "theme", "custom_prompt", "art_style", "language", "voice",
            "length", "difficulty", "model_used", "synopsis", "tags", "cover_image_url",
            "status", "progress", "error", "read_count", "likes_count", "shares_count",
            "created_at", "started_at", "finished_at", "pages"
        ]

class GalleryStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GalleryStory
        fields = ['id', 'title', 'creator_name', 'synopsis', 'cover_image_url', 'is_premium']