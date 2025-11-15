from rest_framework import serializers
from .models import StoryProject, StoryPage
from authentication.models import OnboardingStatus
from django.conf import settings
from django.db import transaction

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

    def validate(self, data):
        user = self.context["request"].user
        try:
            subscription = user.subscription
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            subscription = type('obj', (object,), {'plan': 'trial', 'status': 'trialing'})()

        is_master_plan = subscription.plan == 'master' and subscription.status == 'active'
        if is_master_plan:
            return data

        profile = user.profile
        used_styles = set(profile.used_art_styles.split(',') if profile.used_art_styles else [])
        used_voices = set(profile.used_narrator_voices.split(',') if profile.used_narrator_voices else [])

        submitted_style = data.get('art_style')
        submitted_voice = data.get('voice')
        
        if submitted_style and submitted_style not in used_styles:
            if len(used_styles) >= 5:
                raise serializers.ValidationError({
                    'art_style': "You have already used your 5 available art styles for this trial period. Please upgrade to unlock all styles."
                })
            data['_add_art_style'] = submitted_style 

        if submitted_voice and submitted_voice not in used_voices:
            if len(used_voices) >= 3:
                raise serializers.ValidationError({
                    'voice': "You have already used your 3 available narrator voices for this trial period. Please upgrade to unlock all voices."
                })
            data['_add_narrator_voice'] = submitted_voice 
        
        submitted_theme = data.get('theme')
        if submitted_theme and submitted_theme not in settings.THEME_ID_TO_NAME_MAP:
             raise serializers.ValidationError({
                'theme': f"The theme '{submitted_theme}' is not a valid option."
            })

        return data

    def create(self, validated_data):
        with transaction.atomic():
            user = self.context["request"].user
            hero_data = validated_data.pop('hero')
            
            add_art_style = validated_data.pop('_add_art_style', None)
            add_narrator_voice = validated_data.pop('_add_narrator_voice', None)

            onboarding_profile, _ = OnboardingStatus.objects.get_or_create(user=user)
            for attr, value in hero_data.items():
                setattr(onboarding_profile, attr, value)
            onboarding_profile.save()
            
            profile = user.profile
            update_fields = []
            
            if add_art_style:
                used_styles = set(profile.used_art_styles.split(',') if profile.used_art_styles else [])
                used_styles.add(add_art_style)
                profile.used_art_styles = ",".join(filter(None, used_styles))
                update_fields.append('used_art_styles')
                
            if add_narrator_voice:
                used_voices = set(profile.used_narrator_voices.split(',') if profile.used_narrator_voices else [])
                used_voices.add(add_narrator_voice)
                profile.used_narrator_voices = ",".join(filter(None, used_voices))
                update_fields.append('used_narrator_voices')
            
            if update_fields:
                profile.save(update_fields=update_fields)

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