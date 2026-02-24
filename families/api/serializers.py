"""
Family Tree API Serializers

REST Framework serializers for Person and Relationship models,
supporting interactive family tree visualization and editing.
"""

from rest_framework import serializers
from families.models import Person, Relationship, FamilySpace


class PersonListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for person lists and tree nodes.
    """
    full_name = serializers.SerializerMethodField()
    birth_year = serializers.SerializerMethodField()
    death_year = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Person
        fields = [
            'id', 'first_name', 'last_name', 'maiden_name', 'full_name',
            'gender', 'birth_date', 'birth_year', 'death_date', 'death_year',
            'birth_place', 'death_place', 'photo_url', 'is_private',
        ]
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_birth_year(self, obj):
        return obj.birth_date.year if obj.birth_date else None
    
    def get_death_year(self, obj):
        return obj.death_date.year if obj.death_date else None
    
    def get_photo_url(self, obj):
        if obj.photo:
            return obj.photo.url
        return None


class PersonDetailSerializer(serializers.ModelSerializer):
    """
    Full serializer for person details and editing.
    """
    full_name = serializers.SerializerMethodField()
    parents = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    spouses = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Person
        fields = [
            'id', 'first_name', 'last_name', 'maiden_name', 'full_name',
            'gender', 'birth_date', 'death_date', 'birth_place', 'death_place',
            'birth_date_qualifier', 'death_date_qualifier',
            'photo_url', 'is_private', 'notes',
            'parents', 'children', 'spouses',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_photo_url(self, obj):
        if obj.photo:
            return obj.photo.url
        return None
    
    def get_parents(self, obj):
        return [{'id': p.id, 'name': p.full_name, 'gender': p.gender} for p in obj.parents]
    
    def get_children(self, obj):
        return [{'id': c.id, 'name': c.full_name, 'gender': c.gender} for c in obj.children]
    
    def get_spouses(self, obj):
        return [{'id': s.id, 'name': s.full_name, 'gender': s.gender} for s in obj.spouses]


class PersonCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating persons via API.
    """
    class Meta:
        model = Person
        fields = [
            'id', 'first_name', 'last_name', 'maiden_name',
            'gender', 'birth_date', 'death_date', 'birth_place', 'death_place',
            'birth_date_qualifier', 'death_date_qualifier',
            'is_private', 'notes',
        ]
        read_only_fields = ['id']


class RelationshipSerializer(serializers.ModelSerializer):
    """
    Serializer for relationships between persons.
    """
    person1_name = serializers.SerializerMethodField()
    person2_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Relationship
        fields = [
            'id', 'person1', 'person2', 'person1_name', 'person2_name',
            'relationship_type', 'start_date', 'end_date', 'notes',
        ]
        read_only_fields = ['id']
    
    def get_person1_name(self, obj):
        return obj.person1.full_name
    
    def get_person2_name(self, obj):
        return obj.person2.full_name


class FamilyTreeSerializer(serializers.Serializer):
    """
    Serializer for the complete family tree structure.
    Returns data in a format suitable for D3.js visualization.
    """
    persons = PersonListSerializer(many=True)
    relationships = RelationshipSerializer(many=True)
    
    def _get_linked_user_photo(self, person):
        """Get profile picture from linked user if available."""
        try:
            # Check via linked_membership (Membership.linked_person FK)
            # Uses prefetched data when available
            memberships = list(person.linked_membership.all())
            if memberships:
                membership = memberships[0]
                if hasattr(membership.user, 'profile'):
                    profile = membership.user.profile
                    if profile.profile_picture:
                        return profile.profile_picture.url
            
            # Also check via UserProfile.linked_person (reverse lookup)
            from accounts.models import UserProfile
            profile = UserProfile.objects.filter(linked_person=person).select_related('user').first()
            if profile and profile.profile_picture:
                return profile.profile_picture.url
        except Exception:
            pass
        return None
    
    def to_representation(self, instance):
        """
        Transform data into D3.js-friendly format.
        
        Returns:
            dict with 'nodes' (persons) and 'links' (relationships)
        """
        persons = instance.get('persons', [])
        relationships = instance.get('relationships', [])
        
        # Create nodes for D3.js
        nodes = []
        for p in persons:
            # Person's own photo takes priority, then linked user's profile pic
            photo_url = None
            if p.photo:
                photo_url = p.photo.url
            else:
                # Try to get linked user's profile picture
                photo_url = self._get_linked_user_photo(p)
            
            nodes.append({
                'id': p.id,
                'name': p.full_name,
                'firstName': p.first_name,
                'lastName': p.last_name,
                'gender': p.gender,
                'birthYear': p.birth_date.year if p.birth_date else None,
                'deathYear': p.death_date.year if p.death_date else None,
                'birthPlace': p.birth_place,
                'photoUrl': photo_url,
                'isPrivate': p.is_private,
            })
        
        # Create links for D3.js (parent-child and spouse)
        links = []
        parent_child_links = []
        spouse_links = []
        
        for rel in relationships:
            link_data = {
                'id': rel.id,
                'source': rel.person1_id,
                'target': rel.person2_id,
                'type': rel.relationship_type,
            }
            
            if rel.relationship_type == 'PARENT_CHILD':
                parent_child_links.append(link_data)
            elif rel.relationship_type == 'SPOUSE':
                spouse_links.append(link_data)
            
            links.append(link_data)
        
        return {
            'nodes': nodes,
            'links': links,
            'parentChildLinks': parent_child_links,
            'spouseLinks': spouse_links,
        }
