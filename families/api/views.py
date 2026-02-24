"""
Family Tree API Views

REST Framework viewsets for CRUD operations on Person and Relationship models,
with special endpoints for family tree visualization data.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q

from families.models import Person, Relationship, FamilySpace, Membership
from .serializers import (
    PersonListSerializer, PersonDetailSerializer, PersonCreateUpdateSerializer,
    RelationshipSerializer, FamilyTreeSerializer
)


class IsFamilyMember(permissions.BasePermission):
    """
    Permission check for family membership.
    """
    def has_permission(self, request, view):
        family_id = view.kwargs.get('family_id')
        if not family_id:
            return False
        return Membership.objects.filter(
            user=request.user,
            family_id=family_id
        ).exists()


class CanEditFamily(permissions.BasePermission):
    """
    Permission check for editing (not VIEWER role).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        family_id = view.kwargs.get('family_id')
        if not family_id:
            return False
        
        membership = Membership.objects.filter(
            user=request.user,
            family_id=family_id
        ).first()
        
        if not membership:
            return False
        
        return membership.role in ['OWNER', 'ADMIN', 'EDITOR']


class PersonViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Person CRUD operations.
    
    GET /api/families/{family_id}/persons/ - List all persons
    GET /api/families/{family_id}/persons/{id}/ - Get person details
    POST /api/families/{family_id}/persons/ - Create person
    PATCH /api/families/{family_id}/persons/{id}/ - Update person
    DELETE /api/families/{family_id}/persons/{id}/ - Delete person
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember, CanEditFamily]
    
    def get_queryset(self):
        family_id = self.kwargs.get('family_id')
        return Person.objects.filter(family_id=family_id).select_related('linked_user')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PersonListSerializer
        elif self.action == 'retrieve':
            return PersonDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PersonCreateUpdateSerializer
        return PersonDetailSerializer
    
    def perform_create(self, serializer):
        family_id = self.kwargs.get('family_id')
        family = get_object_or_404(FamilySpace, id=family_id)
        serializer.save(family=family, created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_parent(self, request, family_id=None, pk=None):
        """Add a parent relationship to this person."""
        person = self.get_object()
        parent_id = request.data.get('parent_id')
        
        if not parent_id:
            return Response(
                {'error': 'parent_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        parent = get_object_or_404(Person, id=parent_id, family_id=family_id)
        
        # Check if relationship already exists
        exists = Relationship.objects.filter(
            family_id=family_id,
            person1=parent,
            person2=person,
            relationship_type=Relationship.Type.PARENT_CHILD
        ).exists()
        
        if exists:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        relationship = Relationship.objects.create(
            family_id=family_id,
            person1=parent,
            person2=person,
            relationship_type=Relationship.Type.PARENT_CHILD
        )
        
        return Response(
            RelationshipSerializer(relationship).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def add_spouse(self, request, family_id=None, pk=None):
        """Add a spouse relationship to this person."""
        person = self.get_object()
        spouse_id = request.data.get('spouse_id')
        
        if not spouse_id:
            return Response(
                {'error': 'spouse_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        spouse = get_object_or_404(Person, id=spouse_id, family_id=family_id)
        
        # Check if relationship already exists (either direction)
        exists = Relationship.objects.filter(
            Q(person1=person, person2=spouse) | Q(person1=spouse, person2=person),
            family_id=family_id,
            relationship_type=Relationship.Type.SPOUSE
        ).exists()
        
        if exists:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        relationship = Relationship.objects.create(
            family_id=family_id,
            person1=person,
            person2=spouse,
            relationship_type=Relationship.Type.SPOUSE,
            start_date=request.data.get('marriage_date')
        )
        
        return Response(
            RelationshipSerializer(relationship).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def add_child(self, request, family_id=None, pk=None):
        """Add a child relationship to this person."""
        person = self.get_object()
        child_id = request.data.get('child_id')
        
        if not child_id:
            return Response(
                {'error': 'child_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        child = get_object_or_404(Person, id=child_id, family_id=family_id)
        
        # Check if relationship already exists
        exists = Relationship.objects.filter(
            family_id=family_id,
            person1=person,
            person2=child,
            relationship_type=Relationship.Type.PARENT_CHILD
        ).exists()
        
        if exists:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        relationship = Relationship.objects.create(
            family_id=family_id,
            person1=person,
            person2=child,
            relationship_type=Relationship.Type.PARENT_CHILD
        )
        
        return Response(
            RelationshipSerializer(relationship).data,
            status=status.HTTP_201_CREATED
        )


class RelationshipViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Relationship CRUD operations.
    
    GET /api/families/{family_id}/relationships/ - List all relationships
    POST /api/families/{family_id}/relationships/ - Create relationship
    DELETE /api/families/{family_id}/relationships/{id}/ - Delete relationship
    """
    serializer_class = RelationshipSerializer
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember, CanEditFamily]
    
    def get_queryset(self):
        family_id = self.kwargs.get('family_id')
        return Relationship.objects.filter(family_id=family_id).select_related('person1', 'person2')
    
    def perform_create(self, serializer):
        family_id = self.kwargs.get('family_id')
        family = get_object_or_404(FamilySpace, id=family_id)
        serializer.save(family=family)


class FamilyTreeAPIView(APIView):
    """
    API endpoint returning the complete family tree in D3.js-friendly format.
    
    GET /api/families/{family_id}/tree/
    
    Returns:
        {
            "nodes": [...persons...],
            "links": [...relationships...],
            "parentChildLinks": [...],
            "spouseLinks": [...]
        }
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]
    
    def get(self, request, family_id):
        family = get_object_or_404(FamilySpace, id=family_id)
        
        # Check membership
        if not Membership.objects.filter(
            user=request.user,
            family=family
        ).exists():
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        persons = Person.objects.filter(family=family, is_deleted=False).prefetch_related(
            'linked_membership__user__profile'
        )
        relationships = Relationship.objects.filter(family=family, is_deleted=False).select_related('person1', 'person2')
        
        serializer = FamilyTreeSerializer(instance={
            'persons': persons,
            'relationships': relationships,
        })
        
        return Response(serializer.data)


class PersonSearchAPIView(APIView):
    """
    API endpoint for searching persons within a family.
    
    GET /api/families/{family_id}/persons/search/?q=query
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]
    
    def get(self, request, family_id):
        query = request.query_params.get('q', '').strip()
        
        if len(query) < 2:
            return Response({'results': []})
        
        persons = Person.objects.filter(
            family_id=family_id
        ).filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(maiden_name__icontains=query)
        )[:20]
        
        serializer = PersonListSerializer(persons, many=True)
        return Response({'results': serializer.data})
