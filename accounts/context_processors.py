"""
Accounts App - Context Processors

Django context processors that make data available to all templates.

Context Variables Added:
    - user_profile: Current user's UserProfile instance (or None if anonymous)

Configuration:
    Add 'accounts.context_processors.user_profile' to TEMPLATES context_processors
    in settings.py to enable this processor globally.

Usage in Templates:
    {% if user_profile %}
        <img src="{{ user_profile.get_profile_picture_url }}">
        <span>{{ user_profile.get_display_name }}</span>
    {% endif %}
"""
from .models import UserProfile


def user_profile(request):
    """
    Add the current user's profile to the template context.
    
    Creates a UserProfile if one doesn't exist for authenticated users.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        dict: Context containing 'user_profile' key
            - For authenticated users: UserProfile instance
            - For anonymous users: None
    
    Note:
        This processor auto-creates profiles to avoid DoesNotExist errors.
        This is useful when using the post_save signal for profile creation
        isn't reliable (e.g., users created via manage.py createsuperuser).
    """
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
        return {'user_profile': profile}
    return {'user_profile': None}
