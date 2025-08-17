# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, AuthToken, PasswordHistory, UserActivityLog, OnboardingStatus


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'  # This correctly links to the 'user' field in UserProfile


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')
    list_select_related = ('profile', )

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)


# Unregister the default User model
admin.site.unregister(User)
# Register the custom user admin
admin.site.register(User, CustomUserAdmin)


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token_type', 'short_token', 'created_at', 'expires_at', 'is_valid')
    list_filter = ('token_type', 'is_used')
    search_fields = ('user__username', 'token')
    readonly_fields = ('token', 'created_at', 'expires_at', 'is_valid')

    def short_token(self, obj):
        return str(obj.token)[:8]

    short_token.short_description = 'Token'

    def is_valid(self, obj):
        return obj.is_valid()
    is_valid.boolean = True


@admin.register(PasswordHistory)
class PasswordHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'timestamp', 'ip_address')
    search_fields = ('user__username', 'activity_type')
    readonly_fields = ('timestamp',)
    list_filter = ('activity_type',)


@admin.register(OnboardingStatus)
class OnboardingStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'child_name', 'age', 'pronouns', 'favourite_animal')
    search_fields = ('user__username',)
    list_filter = ('age',)