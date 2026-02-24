"""
Accounts App - URLs

URL patterns for user profiles and messaging.
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Profile views
    path('profile/', views.my_profile, name='my_profile'),
    path('profile/<int:user_id>/', views.profile_view, name='profile_view'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/picture/', views.profile_picture_update, name='profile_picture_update'),
    path('profile/cover/', views.cover_photo_update, name='cover_photo_update'),
    
    # Wall posts
    path('profile/<int:user_id>/post/', views.wall_post_create, name='wall_post_create'),
    path('post/<int:post_id>/edit/', views.wall_post_edit, name='wall_post_edit'),
    path('post/<int:post_id>/delete/', views.wall_post_delete, name='wall_post_delete'),
    path('post/<int:post_id>/comment/', views.wall_post_comment, name='wall_post_comment'),
    path('comment/<int:comment_id>/delete/', views.wall_comment_delete, name='wall_comment_delete'),
    
    # Messages
    path('messages/', views.message_inbox, name='message_inbox'),
    path('messages/sent/', views.message_sent, name='message_sent'),
    path('messages/compose/', views.message_compose, name='message_compose'),
    path('messages/compose/<int:recipient_id>/', views.message_compose, name='message_compose_to'),
    path('messages/<int:message_id>/', views.message_view, name='message_view'),
    path('messages/<int:message_id>/delete/', views.message_delete, name='message_delete'),
    
    # Family tree linking
    path('profile/link-to-tree/', views.link_to_tree, name='link_to_tree'),
    path('profile/unlink-from-tree/', views.unlink_from_tree, name='unlink_from_tree'),
    path('api/family/<int:family_id>/persons/', views.get_family_persons, name='get_family_persons'),
]
