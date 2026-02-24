"""
Context processors for the accounts app.
"""
from .models import UserProfile


def user_profile(request):
    """
    Add the current user's profile to the template context.
    """
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
        return {'user_profile': profile}
    return {'user_profile': None}
