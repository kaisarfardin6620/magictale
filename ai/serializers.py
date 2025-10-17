from rest_framework import serializers
from .models import StoryProject, StoryPage
from authentication.models import OnboardingStatus
from django.conf import settings

class StoryPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryPage
        fields = ["index", "text", "audio_url"]

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

    # vvv --- REPLACE THIS ENTIRE METHOD WITH THE DEBUG VERSION --- vvv
    def validate(self, data):
        """
        [DEBUGGING VERSION] Validates the chosen art style and voice.
        """
        user = self.context["request"].user
        print("\n--- STARTING VALIDATION ---")
        try:
            subscription = user.subscription
            print(f"User '{user.username}' found with subscription.")
            print(f"  -> Plan: '{subscription.plan}'")
            print(f"  -> Status: '{subscription.status}'")
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            subscription = type('obj', (object,), {'plan': 'trial', 'status': 'trialing'})()
            print("User has no subscription object. Using default trial status.")

        is_master_plan = subscription.plan == 'master' and subscription.status == 'active'
        print(f"Is Master Plan? -> {is_master_plan}")

        allowed_voices = settings.ALL_NARRATOR_VOICES if is_master_plan else settings.TIER_1_NARRATOR_VOICES
        print(f"Allowed Voices: {allowed_voices}")

        submitted_voice = data.get('voice')
        print(f"Submitted Voice: '{submitted_voice}'")
        
        if submitted_voice and submitted_voice not in allowed_voices:
            print("--- VALIDATION FAILED: Submitted voice not in allowed list. ---")
            raise serializers.ValidationError({
                'voice': f"The selected narrator voice is not available for your current plan."
            })
        
        print("--- VALIDATION PASSED ---\n")
        # ... (the rest of the validation remains the same)
        submitted_style = data.get('art_style')
        allowed_styles = settings.ALL_ART_STYLES if is_master_plan else settings.TIER_1_ART_STYLES
        if submitted_style and submitted_style not in allowed_styles:
            raise serializers.ValidationError({
                'art_style': f"The '{submitted_style}' art style is not available for your current plan."
            })
            
        submitted_theme = data.get('theme')
        if submitted_theme and submitted_theme not in settings.ALL_THEMES:
             raise serializers.ValidationError({
                'theme': f"The theme '{submitted_theme}' is not a valid option."
            })

        return data

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
    page_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    class Meta:
        model = StoryProject
        depth = 0
        fields = [
            "id", "user", "onboarding", "is_saved", "child_name", "age", "pronouns", "favorite_animal", 
            "favorite_color", "theme", "custom_prompt", "art_style", "language", "voice", "length", 
            "difficulty", "model_used", "synopsis", "tags", "status", "progress", "error", "read_count", 
            "likes_count", "shares_count", "created_at", "started_at", "finished_at", "text", "image_url", "audio_url",
            "page_count" 
        ]
    def get_page_count(self, obj):
        return obj.pages.count()
        
    def get_image_url(self, obj):
        return obj.image_url if obj.image_url else None

    def get_audio_url(self, obj):
        if obj.audio_url:
            if settings.USE_S3_STORAGE:
                return obj.audio_url
            return f"{settings.BACKEND_BASE_URL}{obj.audio_url}"
        return None