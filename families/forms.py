"""
Families App - Forms

This module contains Django ModelForms for the families application.
Forms provide server-side validation and sanitization of user input.

Forms:
    - FamilySpaceCreateForm: Create a new family space
    - InviteCreateForm: Create an invitation to join a family

Security Considerations (OWASP):
    - Django forms automatically handle CSRF protection
    - ModelForms validate against model field constraints
    - Only specified fields are accepted (prevents mass assignment)
    - Django auto-escapes output in templates
"""

from django import forms
from .models import (
    FamilySpace, Invite, Membership, Post, Comment, Event, Person, Relationship,
    Album, Photo, ChatMessage, ChatConversationMessage, DNAKit, DNAMatch,
    LifeStorySection, TimeCapsule, FamilyMilestone, FamilyKudos
)


class FamilySpaceCreateForm(forms.ModelForm):
    """
    Form for creating a new FamilySpace.
    
    This form only exposes user-editable fields. The created_by field
    is set in the view based on the authenticated user, not from form data.
    
    Fields:
        name (str): Required. Display name for the family space (max 120 chars)
        description (str): Optional. Longer description of the family
    
    Security Notes:
        - created_by is NOT in fields (set server-side to prevent spoofing)
        - Django's CharField max_length is enforced at form validation
        - Template rendering auto-escapes output
    
    Example:
        >>> form = FamilySpaceCreateForm(request.POST)
        >>> if form.is_valid():
        ...     family = form.save(commit=False)
        ...     family.created_by = request.user
        ...     family.save()
    """
    
    class Meta:
        model = FamilySpace
        fields = ["name", "description"]
        
        # Optional: customize widgets and labels
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Enter family name',
                'class': 'form-control',
                'maxlength': '120',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Optional description of your family space',
                'class': 'form-control',
                'rows': 3,
            }),
        }
        labels = {
            'name': 'Family Name',
            'description': 'Description',
        }
        help_texts = {
            'name': 'Choose a meaningful name for your family space',
            'description': 'Add an optional description to help members understand the purpose',
        }


class InviteCreateForm(forms.ModelForm):
    """
    Form for creating an invitation to join a FamilySpace.
    
    This form collects the invitee's email and their intended role.
    Other fields (family, created_by, token, expires_at) are set server-side.
    
    Fields:
        email (str): Required. Email address to send the invitation to
        role (str): Required. Role to assign when invite is accepted
    
    Security Notes:
        - family, created_by, token fields NOT exposed (set server-side)
        - Email field validates format via Django's EmailField
        - Role choices are restricted to Membership.Role.choices
        - Token is auto-generated in model save() method
    
    Example:
        >>> form = InviteCreateForm(request.POST)
        >>> if form.is_valid():
        ...     invite = form.save(commit=False)
        ...     invite.family = family_space
        ...     invite.created_by = request.user
        ...     invite.save()  # Token auto-generated
    """
    
    class Meta:
        model = Invite
        fields = ["email", "role"]
        
        widgets = {
            'email': forms.EmailInput(attrs={
                'placeholder': 'Enter email address',
                'class': 'form-control',
            }),
            'role': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
        labels = {
            'email': 'Email Address',
            'role': 'Member Role',
        }
        help_texts = {
            'email': 'The invitation will be sent to this email address',
            'role': 'Select the permission level for the new member',
        }


# =============================================================================
# Phase 2: Social Feed Forms
# =============================================================================

class PostCreateForm(forms.ModelForm):
    """
    Form for creating a post in the family feed.
    
    Allows users to write text and optionally attach an image.
    The family and author fields are set server-side.
    
    Fields:
        content (str): Required. The post text content
        image (ImageField): Optional. Image attachment
    
    Security Notes:
        - family and author NOT in fields (set server-side)
        - Image validation handled by Django's ImageField
        - Max upload size should be configured in settings/nginx
    """
    
    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tagged_people"].queryset = Person.objects.none()
        if family is not None:
            self.fields["tagged_people"].queryset = Person.objects.filter(
                family=family,
                is_deleted=False,
                linked_user__isnull=False,
                death_date__isnull=True,
            ).order_by("last_name", "first_name")

    class Meta:
        model = Post
        fields = ["content", "image", "video", "tagged_people"]
        
        widgets = {
            'content': forms.Textarea(attrs={
                'placeholder': 'Share something with your family...',
                'class': 'form-control',
                'rows': 4,
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*',
            }),
            'tagged_people': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': 6,
            }),
        }
        labels = {
            'content': '',
            'image': 'Add Photo',
            'video': 'Add Video',
            'tagged_people': 'Tag Family Members',
        }


class CommentForm(forms.ModelForm):
    """
    Form for adding a comment to a post.
    
    Simple form for comment text. Post and author are set server-side.
    
    Fields:
        content (str): Required. The comment text
    
    Security Notes:
        - post and author NOT in fields (set server-side)
        - Auto-escaping prevents XSS in comments
    """
    
    class Meta:
        model = Comment
        fields = ["content"]
        
        widgets = {
            'content': forms.Textarea(attrs={
                'placeholder': 'Write a comment...',
                'class': 'form-control',
                'rows': 2,
            }),
        }
        labels = {
            'content': '',
        }


# =============================================================================
# Phase 3: Events & Calendar Forms
# =============================================================================

class EventCreateForm(forms.ModelForm):
    """
    Form for creating a family event.
    
    Collects event details including title, type, datetime, and location.
    The family and created_by fields are set server-side.
    
    Fields:
        title (str): Required. Event title
        description (str): Optional. Event details
        event_type (str): Required. Category of event
        start_datetime (datetime): Required. When event starts
        end_datetime (datetime): Optional. When event ends
        location (str): Optional. Event location
    
    Security Notes:
        - family and created_by NOT in fields (set server-side)
        - DateTime fields use HTML5 datetime-local input for proper validation
    """
    
    REMINDER_CHOICES = [
        (1, "1 day before"),
        (3, "3 days before"),
        (7, "1 week before"),
        (14, "2 weeks before"),
        (30, "1 month before"),
    ]

    reminder_days_before = forms.TypedChoiceField(
        choices=REMINDER_CHOICES,
        coerce=int,
        empty_value=7,
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "event_type",
            "start_datetime",
            "end_datetime",
            "location",
            "image",
            "notify_members",
            "send_reminders",
            "reminder_days_before",
        ]
        
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Event title',
                'class': 'form-control',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Event description and details...',
                'class': 'form-control',
                'rows': 3,
            }),
            'event_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'start_datetime': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }),
            'end_datetime': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }),
            'location': forms.TextInput(attrs={
                'placeholder': 'Location or address',
                'class': 'form-control',
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'notify_members': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'send_reminders': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'reminder_days_before': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
        labels = {
            'title': 'Event Title',
            'description': 'Description',
            'event_type': 'Event Type',
            'start_datetime': 'Start Date & Time',
            'end_datetime': 'End Date & Time (optional)',
            'location': 'Location',
            'image': 'Event Image (optional)',
            'notify_members': 'Notify family members',
            'send_reminders': 'Enable reminders',
            'reminder_days_before': 'Reminder timing',
        }

    def clean(self):
        cleaned_data = super().clean()
        start_datetime = cleaned_data.get("start_datetime")
        end_datetime = cleaned_data.get("end_datetime")
        if start_datetime and end_datetime and end_datetime < start_datetime:
            self.add_error("end_datetime", "End time must be after the start time.")
        return cleaned_data


# =============================================================================
# Phase 4: Family Tree Forms
# =============================================================================

class PersonForm(forms.ModelForm):
    """
    Form for creating/editing a person in the family tree.
    
    Collects personal details including name, dates, and biography.
    Also allows linking to existing family members (father, mother, spouse, children).
    The family and created_by fields are set server-side.
    
    Fields:
        first_name (str): Required
        last_name (str): Required
        maiden_name (str): Optional
        gender (str): Required
        birth_date (date): Optional
        death_date (date): Optional
        birth_place (str): Optional
        death_place (str): Optional
        bio (str): Optional
        photo (ImageField): Optional
        father (Person): Optional - link to father
        mother (Person): Optional - link to mother
        spouse (Person): Optional - link to spouse
        children (Person[]): Optional - link to children
    
    Security Notes:
        - family and created_by NOT in fields (set server-side)
    """
    
    # Relationship fields (not part of the Person model)
    father = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Father'
    )
    mother = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Mother'
    )
    spouse = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Spouse'
    )
    other_parent = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Children's Other Parent",
        help_text="The other parent of the children below (if different from spouse)"
    )
    children = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'}),
        label='Children',
        help_text='Hold Ctrl/Cmd to select multiple'
    )
    
    class Meta:
        model = Person
        fields = [
            "first_name", "last_name", "maiden_name", "gender",
            "birth_date", "death_date", "birth_place", "death_place",
            "bio", "photo"
        ]
        
        widgets = {
            'first_name': forms.TextInput(attrs={
                'placeholder': 'First name',
                'class': 'form-control',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Last name',
                'class': 'form-control',
            }),
            'maiden_name': forms.TextInput(attrs={
                'placeholder': 'Birth surname (if different)',
                'class': 'form-control',
            }),
            'gender': forms.Select(attrs={
                'class': 'form-control',
            }),
            'birth_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'death_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'birth_place': forms.TextInput(attrs={
                'placeholder': 'City, State/Country',
                'class': 'form-control',
            }),
            'death_place': forms.TextInput(attrs={
                'placeholder': 'City, State/Country',
                'class': 'form-control',
            }),
            'bio': forms.Textarea(attrs={
                'placeholder': 'Biography, memories, or stories about this person...',
                'class': 'form-control',
                'rows': 4,
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'maiden_name': 'Maiden Name (optional)',
            'gender': 'Gender',
            'birth_date': 'Date of Birth',
            'death_date': 'Date of Death (if deceased)',
            'birth_place': 'Place of Birth',
            'death_place': 'Place of Death',
            'bio': 'Biography',
            'photo': 'Photo',
        }
    
    def __init__(self, *args, family=None, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        self.family = family
        
        if family:
            # Filter relationship fields to only show people in this family
            family_persons = Person.objects.filter(family=family).order_by('last_name', 'first_name')
            
            # If editing, exclude the person being edited from relationship choices
            if instance:
                family_persons = family_persons.exclude(id=instance.id)
            
            self.fields['father'].queryset = family_persons
            self.fields['mother'].queryset = family_persons
            self.fields['spouse'].queryset = family_persons
            self.fields['other_parent'].queryset = family_persons
            self.fields['children'].queryset = family_persons
            
            # Pre-populate relationship fields if editing an existing person
            if instance:
                # Find father (person1 is parent, this person is child)
                father_rel = Relationship.objects.filter(
                    person2=instance,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                    person1__gender=Person.Gender.MALE
                ).first()
                if father_rel:
                    self.fields['father'].initial = father_rel.person1
                
                # Find mother
                mother_rel = Relationship.objects.filter(
                    person2=instance,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                    person1__gender=Person.Gender.FEMALE
                ).first()
                if mother_rel:
                    self.fields['mother'].initial = mother_rel.person1
                
                # Find spouse
                spouse_rel = Relationship.objects.filter(
                    person1=instance,
                    relationship_type=Relationship.Type.SPOUSE
                ).first() or Relationship.objects.filter(
                    person2=instance,
                    relationship_type=Relationship.Type.SPOUSE
                ).first()
                if spouse_rel:
                    self.fields['spouse'].initial = spouse_rel.person2 if spouse_rel.person1 == instance else spouse_rel.person1
                
                # Find children (this person is parent, children are person2)
                children_rels = Relationship.objects.filter(
                    person1=instance,
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
                if children_rels.exists():
                    self.fields['children'].initial = [r.person2 for r in children_rels]


class RelationshipForm(forms.ModelForm):
    """
    Form for creating a relationship between two people.
    
    Used for adding parent-child or spouse relationships.
    """
    
    class Meta:
        model = Relationship
        fields = ["person2", "relationship_type", "start_date", "end_date", "notes"]
        
        widgets = {
            'person2': forms.Select(attrs={
                'class': 'form-control',
            }),
            'relationship_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'notes': forms.Textarea(attrs={
                'placeholder': 'Additional notes...',
                'class': 'form-control',
                'rows': 2,
            }),
        }
        labels = {
            'person2': 'Related Person',
            'relationship_type': 'Relationship Type',
            'start_date': 'Start Date (e.g., marriage date)',
            'end_date': 'End Date (optional)',
            'notes': 'Notes',
        }
    
    def __init__(self, *args, family=None, exclude_person=None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            queryset = Person.objects.filter(family=family)
            if exclude_person:
                queryset = queryset.exclude(id=exclude_person.id)
            self.fields['person2'].queryset = queryset


class GedcomUploadForm(forms.Form):
    """
    Form for uploading a GEDCOM file to import family tree data.
    
    GEDCOM is the standard format used by Ancestry, FamilySearch,
    and other genealogy software.
    
    Security Notes:
        - File size limited to 5MB
        - Only .ged files accepted
        - Content is parsed and sanitized before import
    """
    
    gedcom_file = forms.FileField(
        label='GEDCOM File',
        help_text='Upload a .ged file exported from Ancestry, FamilySearch, or other genealogy software',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.ged,.gedcom',
        })
    )
    
    def clean_gedcom_file(self):
        """Validate the uploaded GEDCOM file."""
        file = self.cleaned_data.get('gedcom_file')
        
        if file:
            # Check file extension
            if not file.name.lower().endswith(('.ged', '.gedcom')):
                raise forms.ValidationError('Please upload a valid GEDCOM file (.ged or .gedcom)')
            
            # Check file size (5MB max)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must be under 5MB')
        
        return file


# =============================================================================
# Phase 5: Photo Album Forms
# =============================================================================

class AlbumForm(forms.ModelForm):
    """
    Form for creating/editing a photo album.
    
    Fields:
        title: Album name
        description: Optional description
        
    Security Notes:
        - family and created_by are set server-side
    """
    
    class Meta:
        model = Album
        fields = ['title', 'description', 'event', 'primary_person', 'media_focus']
        
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Album title (e.g., "Christmas 2025")',
                'class': 'form-control',
                'maxlength': '200',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Optional description of this album...',
                'class': 'form-control',
                'rows': 3,
            }),
            'event': forms.Select(attrs={
                'class': 'form-control',
            }),
            'primary_person': forms.Select(attrs={
                'class': 'form-control',
            }),
            'media_focus': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
        labels = {
            'title': 'Album Title',
            'description': 'Description',
            'event': 'Event (optional)',
            'primary_person': 'Person (optional)',
            'media_focus': 'Album Type',
        }

    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            self.fields['event'].queryset = Event.objects.filter(family=family).order_by('-start_datetime')
            self.fields['primary_person'].queryset = Person.objects.filter(family=family, is_deleted=False).order_by('last_name', 'first_name')
        else:
            self.fields['event'].queryset = Event.objects.none()
            self.fields['primary_person'].queryset = Person.objects.none()


class PhotoUploadForm(forms.ModelForm):
    """
    Form for uploading a single photo to an album.
    
    Fields:
        image: The photo file
        caption: Optional caption
        taken_date: When the photo was taken
        taken_location: Where it was taken
        tagged_people: People in the photo
        
    Security Notes:
        - album and uploaded_by are set server-side
        - Image file is validated for type and size
    """
    
    class Meta:
        model = Photo
        fields = [
            'media_type',
            'image',
            'file',
            'caption',
            'taken_date',
            'taken_location',
            'tagged_people',
            'event',
            'primary_person',
        ]
        
        widgets = {
            'media_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*,application/pdf,image/*',
            }),
            'caption': forms.TextInput(attrs={
                'placeholder': 'Add a caption...',
                'class': 'form-control',
                'maxlength': '500',
            }),
            'taken_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'taken_location': forms.TextInput(attrs={
                'placeholder': 'Where was this taken?',
                'class': 'form-control',
            }),
            'tagged_people': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5',
            }),
            'event': forms.Select(attrs={
                'class': 'form-control',
            }),
            'primary_person': forms.Select(attrs={
                'class': 'form-control',
            }),
        }
        labels = {
            'media_type': 'Type',
            'image': 'Photo',
            'file': 'Video or Document',
            'caption': 'Caption',
            'taken_date': 'Date Taken',
            'taken_location': 'Location',
            'tagged_people': 'Tag People',
            'event': 'Event (optional)',
            'primary_person': 'Person (optional)',
        }
    
    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            # Filter tagged_people to only show people in this family
            self.fields['tagged_people'].queryset = Person.objects.filter(
                family=family,
                is_deleted=False,
                linked_user__isnull=False,
                death_date__isnull=True,
            ).order_by('last_name', 'first_name')
            self.fields['event'].queryset = Event.objects.filter(family=family).order_by('-start_datetime')
            self.fields['primary_person'].queryset = Person.objects.filter(family=family, is_deleted=False).order_by('last_name', 'first_name')
        else:
            self.fields['tagged_people'].queryset = Person.objects.none()
            self.fields['event'].queryset = Event.objects.none()
            self.fields['primary_person'].queryset = Person.objects.none()
    
    def clean(self):
        cleaned = super().clean()
        media_type = cleaned.get('media_type') or Photo.MediaType.PHOTO
        image = cleaned.get('image')
        file_field = cleaned.get('file')

        if media_type == Photo.MediaType.PHOTO:
            if not image and not file_field:
                raise forms.ValidationError('Please upload a photo.')
            target = image or file_field
            if target:
                if target.size > 15 * 1024 * 1024:
                    raise forms.ValidationError('Photo must be under 15MB.')
                allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
                if hasattr(target, 'content_type') and target.content_type not in allowed_types:
                    raise forms.ValidationError('Upload a valid image (JPEG, PNG, GIF, WebP).')
            cleaned['image'] = image or file_field
            cleaned['file'] = None

        elif media_type == Photo.MediaType.VIDEO:
            if not file_field:
                raise forms.ValidationError('Upload a video file.')
            if file_field.size > 100 * 1024 * 1024:
                raise forms.ValidationError('Video must be under 100MB.')
            if hasattr(file_field, 'content_type') and not file_field.content_type.startswith('video/'):
                raise forms.ValidationError('Upload a valid video file.')
            cleaned['image'] = None

        elif media_type == Photo.MediaType.DOCUMENT:
            if not file_field:
                raise forms.ValidationError('Upload a document file.')
            if file_field.size > 25 * 1024 * 1024:
                raise forms.ValidationError('Document must be under 25MB.')
            allowed_docs = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/jpeg', 'image/png']
            if hasattr(file_field, 'content_type') and file_field.content_type not in allowed_docs:
                raise forms.ValidationError('Upload PDF, DOC, DOCX, or image scans.')
            cleaned['image'] = None

        return cleaned


class MultiPhotoUploadForm(forms.Form):
    """
    Form for uploading multiple photos at once.
    
    Note: Django FileInput doesn't support multiple=True in the widget,
    so we handle the multiple attribute in the template HTML directly.
    The form just provides validation structure.
    """
    pass  # Multiple file handling done via request.FILES.getlist() in view


# =============================================================================
# Phase 6: Notifications & Messaging Forms
# =============================================================================

class ChatMessageForm(forms.ModelForm):
    """
    Form for sending a chat message in a family group chat.
    
    Fields:
        content (str): The message text (max 2000 chars)
    
    Security Notes:
        - author is set server-side from authenticated user
        - family is set server-side from URL parameter
        - Content is HTML-escaped on display
    """
    
    class Meta:
        model = ChatMessage
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Type a message...',
                'maxlength': 2000,
            })
        }
    
    def clean_content(self):
        """Validate message content."""
        content = self.cleaned_data.get('content', '').strip()
        if not content:
            raise forms.ValidationError('Message cannot be empty')
        if len(content) > 2000:
            raise forms.ValidationError('Message is too long (max 2000 characters)')
        return content


class LifeStorySectionForm(forms.ModelForm):
    class Meta:
        model = LifeStorySection
        fields = ["heading", "content", "audio", "order"]
        widgets = {
            "heading": forms.TextInput(attrs={"class": "form-control", "placeholder": "Section heading"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Add the story for this section..."}),
            "audio": forms.FileInput(attrs={"class": "form-control", "accept": "audio/*"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }


class TimeCapsuleForm(forms.ModelForm):
    class Meta:
        model = TimeCapsule
        fields = ["title", "message", "open_at", "attachment", "audio"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Time capsule title"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Write a message to the future..."}),
            "open_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
            "audio": forms.FileInput(attrs={"class": "form-control", "accept": "audio/*"}),
        }


class FamilyMilestoneForm(forms.ModelForm):
    class Meta:
        model = FamilyMilestone
        fields = ["title", "description", "date", "image", "person", "event"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Milestone title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe the milestone"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "image": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "person": forms.Select(attrs={"class": "form-control"}),
            "event": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            self.fields["person"].queryset = Person.objects.filter(family=family, is_deleted=False).order_by("last_name", "first_name")
            self.fields["event"].queryset = Event.objects.filter(family=family).order_by("-start_datetime")
        else:
            self.fields["person"].queryset = Person.objects.none()
            self.fields["event"].queryset = Event.objects.none()


class FamilyKudosForm(forms.ModelForm):
    class Meta:
        model = FamilyKudos
        fields = ["title", "message", "image", "person"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Headline"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Share the exciting news"}),
            "image": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "person": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)
        if family:
            self.fields["person"].queryset = Person.objects.filter(
                family=family,
                is_deleted=False,
            ).order_by("last_name", "first_name")
        else:
            self.fields["person"].queryset = Person.objects.none()


class ConversationMessageForm(forms.ModelForm):
    """
    Form for sending a message in a unified realtime conversation.
    """

    class Meta:
        model = ChatConversationMessage
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Type a message...",
                "maxlength": 4000,
            })
        }

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if not content:
            raise forms.ValidationError("Message cannot be empty")
        if len(content) > 4000:
            raise forms.ValidationError("Message is too long (max 4000 characters)")
        return content


# =============================================================================
# Phase 8: DNA Assist Tools Forms
# =============================================================================

class DNAKitForm(forms.ModelForm):
    """
    Form for registering a DNA kit.
    
    Fields:
        provider (str): DNA testing company
        kit_id (str): Optional kit identifier
        display_name (str): Friendly name for the kit
        is_private (bool): Whether kit is hidden from others
        allow_matching (bool): Whether to allow DNA matching
        notes (str): Private notes
    
    Security Notes:
        - user is set server-side from authenticated user
        - linked_person must belong to a family the user has access to
    """
    
    class Meta:
        model = DNAKit
        fields = ['provider', 'kit_id', 'display_name', 'is_private', 'allow_matching', 'notes']
        widgets = {
            'provider': forms.Select(attrs={
                'class': 'form-control',
            }),
            'kit_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., A123456 (optional)',
            }),
            'display_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., My AncestryDNA Kit',
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'allow_matching': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Private notes about this kit...',
            }),
        }
        labels = {
            'kit_id': 'Kit ID (from provider)',
            'is_private': 'Keep this kit private',
            'allow_matching': 'Allow DNA matching with other users',
        }
        help_texts = {
            'is_private': 'If checked, other users cannot see this kit',
            'allow_matching': 'If checked, other users with matching enabled can compare DNA',
        }
    
    def clean_display_name(self):
        """Validate display name."""
        name = self.cleaned_data.get('display_name', '').strip()
        if not name:
            raise forms.ValidationError('Display name is required')
        if len(name) > 100:
            raise forms.ValidationError('Display name is too long (max 100 characters)')
        return name


class DNAMatchForm(forms.ModelForm):
    """
    Form for adding a DNA match manually.
    
    Fields:
        shared_cm (float): Shared DNA in centiMorgans
        shared_segments (int): Number of shared segments
        largest_segment (float): Largest segment in cM
        notes (str): Notes about the match
    
    Security Notes:
        - kit1 and kit2 are validated server-side
        - User must own kit1 or have permission
    """
    
    class Meta:
        model = DNAMatch
        fields = ['shared_cm', 'shared_segments', 'largest_segment', 'notes']
        widgets = {
            'shared_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 850',
                'step': '0.1',
                'min': '0',
            }),
            'shared_segments': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 25',
                'min': '0',
            }),
            'largest_segment': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 75.5',
                'step': '0.1',
                'min': '0',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes about this match...',
            }),
        }
        labels = {
            'shared_cm': 'Shared cM (centiMorgans)',
            'shared_segments': 'Number of Shared Segments',
            'largest_segment': 'Largest Segment (cM)',
        }
        help_texts = {
            'shared_cm': 'Total shared DNA in centiMorgans',
            'shared_segments': 'How many DNA segments you share',
            'largest_segment': 'Size of the largest shared segment',
        }
    
    def clean_shared_cm(self):
        """Validate shared cM value."""
        cm = self.cleaned_data.get('shared_cm')
        if cm is None:
            raise forms.ValidationError('Shared cM is required')
        if cm < 0:
            raise forms.ValidationError('Shared cM cannot be negative')
        if cm > 3700:
            raise forms.ValidationError('Shared cM seems too high (max ~3700 for parent/child)')
        return cm


class LinkToTreeForm(forms.Form):
    """
    Form for linking a DNA match to a person in the family tree.
    
    This is used in the attach-to-tree confirmation workflow.
    """
    
    person_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False,
    )
    
    relationship_type = forms.ChoiceField(
        choices=[
            ('', '-- Select Relationship --'),
            ('parent', 'Parent'),
            ('child', 'Child'),
            ('sibling', 'Sibling'),
            ('half_sibling', 'Half-Sibling'),
            ('grandparent', 'Grandparent'),
            ('grandchild', 'Grandchild'),
            ('aunt_uncle', 'Aunt/Uncle'),
            ('niece_nephew', 'Niece/Nephew'),
            ('cousin', 'Cousin'),
            ('other', 'Other Relative'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-control',
        }),
        required=True,
    )
    
    notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Add any notes about this relationship...',
        }),
        required=False,
    )
