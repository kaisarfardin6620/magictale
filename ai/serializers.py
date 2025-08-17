from rest_framework import serializers
from .models import StoryProject, StoryPage

class StoryPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryPage
        fields = ["id", "index", "text", "image_url", "audio_url"]

class StoryProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryProject
        fields = [
            "id", "onboarding", "theme", "art_style", "language",
            "voice", "length", "difficulty", "model_used"
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        return StoryProject.objects.create(user=user, **validated_data)

class StoryProjectDetailSerializer(serializers.ModelSerializer):
    pages = StoryPageSerializer(many=True, read_only=True)

    class Meta:
        model = StoryProject
        fields = [
            "id","user","onboarding","theme","art_style","language","voice",
            "length","difficulty","model_used","status","progress","error",
            "created_at","started_at","finished_at","pages"
        ]
        read_only_fields = ("user","status","progress","error","created_at","started_at","finished_at","pages")
