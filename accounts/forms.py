"""
Accounts App - Forms

Django ModelForms for user profile management and social features.

Forms:
    Profile Management:
        - UserProfileForm: Full profile editing (name, bio, photos, settings)
        - ProfilePictureForm: Quick profile picture upload
        - CoverPhotoForm: Quick cover photo upload
        
    Social Features:
        - ProfilePostForm: Creating and editing wall posts
        - ProfilePostCommentForm: Commenting on wall posts
        - ProfileMessageForm: Sending direct messages

Widget Configuration:
    All forms use Bootstrap-compatible CSS classes for consistent styling.
    File inputs are configured to accept image/* MIME types.
    Date inputs use HTML5 date type for native date pickers.

Security Notes:
    - Only fields specified in Meta.fields are accepted
    - File uploads validated by model constraints
    - Template rendering auto-escapes text content
"""

from django import forms
from .models import UserProfile, ProfilePost, ProfilePostComment, ProfileMessage


class UserProfileForm(forms.ModelForm):
    """
    Comprehensive form for editing user profile information.
    
    Includes personal info, photos, and privacy settings.
    Profile picture and cover photo can be uploaded but cropping
    is handled by separate views with JavaScript croppers.
    
    Fields:
        display_name: Name shown on profile (defaults to email username)
        bio: Personal bio/about text (max 500 chars)
        profile_picture: Avatar image
        cover_photo: Banner image at top of profile
        location: User's location (free text)
        website: Personal website URL
        date_of_birth: Birthday (used for age display, birthday notifications)
        profile_visibility: Who can view the profile
        show_email: Whether to display email on profile
        show_birthday: Whether to display birthday on profile
    """
    
    class Meta:
        model = UserProfile
        fields = [
            'display_name', 'bio', 'profile_picture', 'cover_photo',
            'location', 'website', 'date_of_birth',
            'profile_visibility', 'show_email', 'show_birthday'
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your display name'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Tell us about yourself...'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'cover_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City, Country'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://yourwebsite.com'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'profile_visibility': forms.Select(attrs={
                'class': 'form-control'
            }),
            'show_email': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'show_birthday': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class ProfilePictureForm(forms.ModelForm):
    """
    Quick form for updating profile picture only.
    """
    
    class Meta:
        model = UserProfile
        fields = ['profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }


class CoverPhotoForm(forms.ModelForm):
    """
    Quick form for updating cover photo only.
    """
    
    class Meta:
        model = UserProfile
        fields = ['cover_photo']
        widgets = {
            'cover_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }


class ProfilePostForm(forms.ModelForm):
    """
    Form for creating wall posts.
    """
    
    class Meta:
        model = ProfilePost
        fields = ['content', 'image', 'video', 'visibility']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': "What's on your mind?"
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*'
            }),
            'visibility': forms.Select(attrs={
                'class': 'form-control'
            }),
        }


class ProfilePostCommentForm(forms.ModelForm):
    """
    Form for commenting on wall posts.
    """
    
    class Meta:
        model = ProfilePostComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Write a comment...'
            })
        }


class ProfileMessageForm(forms.ModelForm):
    """
    Form for sending direct messages.
    """
    
    class Meta:
        model = ProfileMessage
        fields = ['subject', 'content']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject (optional)'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Write your message...'
            })
        }


class LinkToPersonForm(forms.Form):
    """
    Form for linking profile to a person in family tree.
    """
    
    family_id = forms.IntegerField(widget=forms.HiddenInput())
    person_id = forms.IntegerField(widget=forms.Select(attrs={
        'class': 'form-control'
    }))
    
    def __init__(self, *args, families=None, **kwargs):
        super().__init__(*args, **kwargs)
        if families:
            # Will be populated dynamically via JS
            pass
