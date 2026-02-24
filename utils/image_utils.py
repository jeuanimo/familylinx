"""
Image utilities for FamilyLinx.
Handles cropped image processing from the frontend cropper.
"""

import base64
import uuid
from io import BytesIO
from django.core.files.base import ContentFile


def process_cropped_image(request, field_name='cropped_image_data'):
    """
    Process a cropped image from a form submission.
    
    The frontend cropper sends base64-encoded image data in a hidden field.
    This function extracts and converts it to a Django ContentFile.
    
    Args:
        request: The Django request object
        field_name: Name of the hidden field containing base64 data
    
    Returns:
        tuple: (ContentFile, filename) or (None, None) if no cropped image
    """
    cropped_data = request.POST.get(field_name, '')
    original_filename = request.POST.get('cropped_image_filename', 'image.jpg')
    
    if not cropped_data or not cropped_data.startswith('data:image'):
        return None, None
    
    try:
        # Parse base64 data: "data:image/jpeg;base64,/9j/4AAQ..."
        format_prefix, imgstr = cropped_data.split(';base64,')
        ext = format_prefix.split('/')[-1]
        if ext == 'jpeg':
            ext = 'jpg'
        
        # Decode base64 to binary
        image_data = base64.b64decode(imgstr)
        
        # Generate unique filename
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        filename = f"{base_name}_{uuid.uuid4().hex[:8]}.{ext}"
        
        return ContentFile(image_data), filename
    
    except Exception as e:
        print(f"Error processing cropped image: {e}")
        return None, None


def save_cropped_to_field(request, instance, field_name, cropped_field='cropped_image_data'):
    """
    Save a cropped image directly to a model's ImageField.
    
    Args:
        request: Django request object
        instance: Model instance with the ImageField
        field_name: Name of the ImageField on the model
        cropped_field: Name of the POST field with cropped data
    
    Returns:
        bool: True if image was saved, False otherwise
    """
    content_file, filename = process_cropped_image(request, cropped_field)
    
    if content_file and filename:
        field = getattr(instance, field_name)
        field.save(filename, content_file, save=True)
        return True
    
    return False
