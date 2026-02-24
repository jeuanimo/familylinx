"""
Accounts App - Admin Configuration

Register profile models for Django admin.
"""

from django.contrib import admin
from .models import UserProfile, ProfilePost, ProfilePostComment, ProfileMessage


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin configuration for UserProfile model."""
    list_display = ('user', 'display_name', 'profile_visibility', 'linked_person', 'created_at')
    list_filter = ('profile_visibility', 'created_at')
    search_fields = ('user__email', 'display_name', 'bio', 'location')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'linked_person')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'display_name', 'bio')
        }),
        ('Images', {
            'fields': ('profile_picture', 'cover_photo'),
        }),
        ('Personal Info', {
            'fields': ('location', 'website', 'date_of_birth'),
        }),
        ('Privacy', {
            'fields': ('profile_visibility', 'show_email', 'show_birthday'),
        }),
        ('Family Tree', {
            'fields': ('linked_person',),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(ProfilePost)
class ProfilePostAdmin(admin.ModelAdmin):
    """Admin configuration for ProfilePost model."""
    list_display = ('id', 'author', 'profile', 'content_preview', 'has_media', 'visibility', 'is_pinned', 'created_at')
    list_filter = ('visibility', 'is_pinned', 'created_at')
    search_fields = ('content', 'author__email', 'profile__user__email')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('author', 'profile')
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
    
    def has_media(self, obj):
        media = []
        if obj.image:
            media.append('📷')
        if obj.video:
            media.append('🎬')
        return ' '.join(media) if media else '-'
    has_media.short_description = 'Media'


@admin.register(ProfilePostComment)
class ProfilePostCommentAdmin(admin.ModelAdmin):
    """Admin configuration for ProfilePostComment model."""
    list_display = ('id', 'author', 'post', 'content_preview', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__email')
    readonly_fields = ('created_at',)
    raw_id_fields = ('post', 'author')
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(ProfileMessage)
class ProfileMessageAdmin(admin.ModelAdmin):
    """Admin configuration for ProfileMessage model."""
    list_display = ('id', 'sender', 'recipient', 'subject', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('subject', 'content', 'sender__email', 'recipient__email')
    readonly_fields = ('created_at', 'read_at')
    raw_id_fields = ('sender', 'recipient')
