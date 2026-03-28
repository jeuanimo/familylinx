"""
Accounts App - URL Configuration

URL patterns for user profiles, wall posts, and direct messaging.
All URLs are namespaced under 'accounts' for reverse URL lookup.

URL Structure:
    /u/directory/                   - Logged-in user directory
    /u/admin/people/                - Staff-only account/profile directory
    /u/profile/                     - Redirect to own profile
    /u/profile/<user_id>/           - View a user's profile
    /u/profile/edit/                - Edit own profile settings
    /u/profile/picture/             - Upload profile picture
    /u/profile/cover/               - Upload cover photo
    
    Wall Posts:
    /u/profile/<user_id>/post/      - Create post on wall
    /u/post/<post_id>/edit/         - Edit a wall post
    /u/post/<post_id>/delete/       - Delete a wall post
    /u/post/<post_id>/comment/      - Add comment
    /u/comment/<id>/delete/         - Delete comment
    
    Direct Messages:
    /u/messages/                    - Inbox
    /u/messages/sent/               - Sent messages
    /u/messages/compose/            - New message
    /u/messages/<id>/               - View message
    
    Tree Linking:
    /u/profile/link-to-tree/        - Link profile to Person
    /u/profile/unlink-from-tree/    - Remove tree link

Namespace:
    Use 'accounts:name' for reverse lookups.
    Example: reverse('accounts:profile_view', kwargs={'user_id': 1})
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # ==========================================================================
    # Profile Views
    # ==========================================================================

    path('access/', views.auth_portal, name='auth_portal'),

    # Directory of users who have logged in
    path('directory/', views.user_directory, name='user_directory'),
    path('admin/people/', views.admin_user_directory, name='admin_user_directory'),
    
    # Redirect to current user's profile
    path('profile/', views.my_profile, name='my_profile'),
    
    # View any user's profile (privacy settings enforced in view)
    path('profile/<int:user_id>/', views.profile_view, name='profile_view'),
    
    # Edit own profile settings
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    
    # Quick photo uploads with crop support
    path('profile/picture/', views.profile_picture_update, name='profile_picture_update'),
    path('profile/cover/', views.cover_photo_update, name='cover_photo_update'),
    
    # ==========================================================================
    # Wall Posts (Facebook-style)
    # ==========================================================================
    
    # Create a post on a user's wall (own wall only)
    path('profile/<int:user_id>/post/', views.wall_post_create, name='wall_post_create'),
    
    # Edit/delete posts and comments (author only)
    path('post/<int:post_id>/edit/', views.wall_post_edit, name='wall_post_edit'),
    path('post/<int:post_id>/delete/', views.wall_post_delete, name='wall_post_delete'),
    path('post/<int:post_id>/comment/', views.wall_post_comment, name='wall_post_comment'),
    path('comment/<int:comment_id>/delete/', views.wall_comment_delete, name='wall_comment_delete'),
    
    # ==========================================================================
    # Direct Messages
    # ==========================================================================
    
    # Message management
    path('messages/', views.message_inbox, name='message_inbox'),
    path('messages/sent/', views.message_sent, name='message_sent'),
    path('messages/compose/', views.message_compose, name='message_compose'),
    path('messages/compose/<int:recipient_id>/', views.message_compose, name='message_compose_to'),
    path('messages/<int:message_id>/', views.message_view, name='message_view'),
    path('messages/<int:message_id>/delete/', views.message_delete, name='message_delete'),
    
    # ==========================================================================
    # Family Tree Linking
    # ==========================================================================
    
    # Link/unlink profile to Person record in family tree
    path('profile/link-to-tree/', views.link_to_tree, name='link_to_tree'),
    path('profile/unlink-from-tree/', views.unlink_from_tree, name='unlink_from_tree'),
    
    # AJAX endpoint for person dropdown (used by link-to-tree form)
    path('api/family/<int:family_id>/persons/', views.get_family_persons, name='get_family_persons'),
]
