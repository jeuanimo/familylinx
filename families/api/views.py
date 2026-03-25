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
from django.utils import timezone
from django.db.models import Q

from families.models import Person, Relationship, FamilySpace, Membership, PendingPersonChange
from .serializers import (
    PersonListSerializer, PersonDetailSerializer, PersonCreateUpdateSerializer,
    RelationshipSerializer, FamilyTreeSerializer, PendingPersonChangeSerializer
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


def _allowed_person_ids_for_member(membership):
    """
    For MEMBER role: allow editing themselves, their spouses, and their children.
    """
    if not membership.linked_person_id:
        return set()
    me_id = membership.linked_person_id
    family_id = membership.family_id
    spouse_ids = set(Relationship.objects.filter(
        family_id=family_id,
        relationship_type=Relationship.Type.SPOUSE,
        person1_id=me_id
    ).values_list('person2_id', flat=True))
    spouse_ids.update(Relationship.objects.filter(
        family_id=family_id,
        relationship_type=Relationship.Type.SPOUSE,
        person2_id=me_id
    ).values_list('person1_id', flat=True))

    # Children of me or any spouse
    parent_ids = {me_id} | spouse_ids
    child_ids = set(Relationship.objects.filter(
        family_id=family_id,
        relationship_type=Relationship.Type.PARENT_CHILD,
        person1_id__in=parent_ids
    ).values_list('person2_id', flat=True))

    return {me_id} | spouse_ids | child_ids


class LimitedEditPermission(permissions.BasePermission):
    """
    Edit permissions:
    - OWNER/ADMIN/EDITOR: full edit
    - MEMBER: can update their own person, spouses, and children; cannot create/delete
    - VIEWER: read-only
    """
    def has_permission(self, request, view):
        # Safe methods already handled by IsFamilyMember
        if request.method in permissions.SAFE_METHODS:
            return True

        family_id = view.kwargs.get('family_id')
        membership = Membership.objects.filter(user=request.user, family_id=family_id).first()
        if not membership:
            return False

        if membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return True

        if membership.role == 'MEMBER':
            # Allow submitting create/update/delete requests (handled as pending)
            return view.action in ['create', 'update', 'partial_update', 'destroy']

        return False

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        family_id = view.kwargs.get('family_id')
        membership = Membership.objects.filter(user=request.user, family_id=family_id).first()
        if not membership:
            return False

        if membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return True

        if membership.role == 'MEMBER':
            allowed_ids = _allowed_person_ids_for_member(membership)
            return obj.id in allowed_ids

        return False


class PersonViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Person CRUD operations.
    
    GET /api/families/{family_id}/persons/ - List all persons
    GET /api/families/{family_id}/persons/{id}/ - Get person details
    POST /api/families/{family_id}/persons/ - Create person
    PATCH /api/families/{family_id}/persons/{id}/ - Update person
    DELETE /api/families/{family_id}/persons/{id}/ - Delete person
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember, LimitedEditPermission]
    
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
    
    def _membership(self):
        family_id = self.kwargs.get('family_id')
        return Membership.objects.filter(user=self.request.user, family_id=family_id).first()

    def create(self, request, *args, **kwargs):
        membership = self._membership()
        if membership and membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return super().create(request, *args, **kwargs)
        family_id = self.kwargs.get('family_id')
        family = get_object_or_404(FamilySpace, id=family_id)
        PendingPersonChange.objects.create(
            family=family,
            action=PendingPersonChange.Action.CREATE,
            payload=request.data,
            created_by=request.user,
        )
        return Response({'detail': 'Submitted for approval'}, status=status.HTTP_202_ACCEPTED)

    def update(self, request, *args, **kwargs):
        membership = self._membership()
        if membership and membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return super().update(request, *args, **kwargs)
        instance = self.get_object()
        PendingPersonChange.objects.create(
            family=instance.family,
            person=instance,
            action=PendingPersonChange.Action.UPDATE,
            payload=request.data,
            created_by=request.user,
        )
        return Response({'detail': 'Update submitted for approval'}, status=status.HTTP_202_ACCEPTED)

    def partial_update(self, request, *args, **kwargs):
        membership = self._membership()
        if membership and membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return super().partial_update(request, *args, **kwargs)
        instance = self.get_object()
        PendingPersonChange.objects.create(
            family=instance.family,
            person=instance,
            action=PendingPersonChange.Action.UPDATE,
            payload=request.data,
            created_by=request.user,
        )
        return Response({'detail': 'Update submitted for approval'}, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        membership = self._membership()
        if membership and membership.role in ['OWNER', 'ADMIN', 'EDITOR']:
            return super().destroy(request, *args, **kwargs)
        instance = self.get_object()
        PendingPersonChange.objects.create(
            family=instance.family,
            person=instance,
            action=PendingPersonChange.Action.DELETE,
            payload={},
            created_by=request.user,
        )
        return Response({'detail': 'Delete submitted for approval'}, status=status.HTTP_202_ACCEPTED)
    
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
        
        persons_qs = Person.objects.filter(family=family, is_deleted=False).prefetch_related(
            'linked_membership__user__profile'
        )
        relationships_qs = Relationship.objects.filter(family=family, is_deleted=False).select_related('person1', 'person2')

        def _to_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        person_param = request.query_params.get('person_id')
        if person_param == 'me':
            focal_id = Membership.objects.filter(user=request.user, family=family).values_list('linked_person_id', flat=True).first()
        elif person_param:
            focal_id = _to_int(person_param)
        else:
            focal_id = Membership.objects.filter(user=request.user, family=family).values_list('linked_person_id', flat=True).first()

        depth_up = _to_int(request.query_params.get('depth_up'))
        depth_down = _to_int(request.query_params.get('depth_down'))
        include_spouses = (request.query_params.get('include_spouses') or '1') not in ['0', 'false', 'False']

        # If no focal or no depth limits are provided, return full tree (existing behavior)
        if not focal_id or (depth_up is None and depth_down is None):
            serializer = FamilyTreeSerializer(
                instance={
                    'persons': persons_qs,
                    'relationships': relationships_qs,
                },
                context={'request': request},
            )
            return Response(serializer.data)

        persons_by_id = {p.id: p for p in persons_qs}
        if focal_id not in persons_by_id:
            return Response({'detail': 'person not found in this family'}, status=status.HTTP_404_NOT_FOUND)

        child_to_parents = {}
        parent_to_children = {}
        spouse_links = []
        for r in relationships_qs:
            if r.relationship_type == Relationship.Type.PARENT_CHILD:
                child_to_parents.setdefault(r.person2_id, []).append(r.person1_id)
                parent_to_children.setdefault(r.person1_id, []).append(r.person2_id)
            elif r.relationship_type == Relationship.Type.SPOUSE:
                spouse_links.append((r.person1_id, r.person2_id))

        included_ids = {focal_id}

        # Ancestors up to depth_up
        if depth_up is not None:
            frontier = [(focal_id, 0)]
            while frontier:
                pid, d = frontier.pop(0)
                if d >= depth_up:
                    continue
                for par_id in child_to_parents.get(pid, []):
                    if par_id not in included_ids:
                        included_ids.add(par_id)
                        frontier.append((par_id, d + 1))

        # Descendants down to depth_down
        if depth_down is not None:
            frontier = [(focal_id, 0)]
            while frontier:
                pid, d = frontier.pop(0)
                if d >= depth_down:
                    continue
                for child_id in parent_to_children.get(pid, []):
                    if child_id not in included_ids:
                        included_ids.add(child_id)
                        frontier.append((child_id, d + 1))

        if include_spouses:
            for a, b in spouse_links:
                if a in included_ids or b in included_ids:
                    included_ids.add(a)
                    included_ids.add(b)

        persons = [persons_by_id[i] for i in included_ids if i in persons_by_id]
        relationships = [r for r in relationships_qs if r.person1_id in included_ids and r.person2_id in included_ids]

        serializer = FamilyTreeSerializer(
            instance={
                'persons': persons,
                'relationships': relationships,
            },
            context={'request': request},
        )
        
        return Response(serializer.data)


class FamilyLineExportAPIView(APIView):
    """
    Export a person's maternal or paternal line as a mini tree (JSON).

    GET /api/families/{family_id}/export/line/?person_id=123&line=maternal|paternal&mode=line|subtree&include_spouses=0|1&parent_hint_id=999&depth_up=3&depth_down=2

    - line: required, which side to follow (defaults to maternal).
    - person_id: defaults to the caller's linked person (if set).
    - mode:
        * line     -> just the direct line ancestors + focal person
        * subtree  -> direct line ancestors + all descendants of the focal person
                      (useful to seed a new space)
    - include_spouses: if truthy, adds spouses of included people to make cards coherent.
    - parent_hint_id: optional disambiguator when multiple mothers/fathers exist; only applied to the first hop.
    - depth_up: optional max generations up the chosen line (0 = only focal; default unlimited)
    - depth_down: optional max generations down (subtree mode only; default unlimited)
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]

    def get(self, request, family_id):
        family = get_object_or_404(FamilySpace, id=family_id)

        membership = Membership.objects.filter(user=request.user, family=family).first()
        if not membership:
            return Response({'detail': 'Not a member'}, status=status.HTTP_403_FORBIDDEN)

        # Params
        person_id = request.query_params.get('person_id')
        if not person_id:
            person_id = membership.linked_person_id
        try:
            focal_id = int(person_id)
        except (TypeError, ValueError):
            return Response({'detail': 'person_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        line = (request.query_params.get('line') or 'maternal').lower()
        if line not in ['maternal', 'paternal']:
            return Response({'detail': 'line must be maternal or paternal'}, status=status.HTTP_400_BAD_REQUEST)
        target_gender = Person.Gender.FEMALE if line == 'maternal' else Person.Gender.MALE

        mode = (request.query_params.get('mode') or 'subtree').lower()
        if mode not in ['line', 'subtree']:
            return Response({'detail': 'mode must be line or subtree'}, status=status.HTTP_400_BAD_REQUEST)

        include_spouses = (request.query_params.get('include_spouses') or '1') not in ['0', 'false', 'False']
        depth_up = request.query_params.get('depth_up')
        depth_down = request.query_params.get('depth_down')
        try:
            depth_up = int(depth_up) if depth_up is not None else None
        except (TypeError, ValueError):
            depth_up = None
        try:
            depth_down = int(depth_down) if depth_down is not None else None
        except (TypeError, ValueError):
            depth_down = None

        persons_qs = Person.objects.filter(family=family, is_deleted=False)
        persons_by_id = {p.id: p for p in persons_qs}
        if focal_id not in persons_by_id:
            return Response({'detail': 'person not found in this family'}, status=status.HTTP_404_NOT_FOUND)

        rels_qs = Relationship.objects.filter(
            family=family,
            is_deleted=False,
            relationship_type__in=[Relationship.Type.PARENT_CHILD, Relationship.Type.SPOUSE]
        ).select_related('person1', 'person2')

        child_to_parents = {}
        parent_to_children = {}
        for r in rels_qs:
            if r.relationship_type == Relationship.Type.PARENT_CHILD:
                child_to_parents.setdefault(r.person2_id, []).append(r.person1_id)
                parent_to_children.setdefault(r.person1_id, []).append(r.person2_id)

        # Optional parent hint for the first hop (helps when multiple mothers/fathers exist)
        parent_hint_id = request.query_params.get('parent_hint_id')
        try:
            parent_hint_id = int(parent_hint_id) if parent_hint_id is not None else None
        except (TypeError, ValueError):
            parent_hint_id = None

        # Build the straight maternal/paternal line (ancestors of chosen gender)
        line_ids = []
        current = focal_id
        line_ids.append(current)
        while True:
            parents = child_to_parents.get(current, [])
            gender_matches = [pid for pid in parents if (pid in persons_by_id and persons_by_id[pid].gender == target_gender)]

            if parent_hint_id and current == focal_id and parent_hint_id in gender_matches:
                next_parent = parent_hint_id
            else:
                def sort_key(pid):
                    p = persons_by_id.get(pid)
                    byear = p.birth_date.year if (p and p.birth_date) else 9999
                    return (byear, pid)
                gender_matches = sorted(gender_matches, key=sort_key)
                next_parent = gender_matches[0] if gender_matches else None

            if not next_parent:
                break
            if next_parent in line_ids:
                break  # avoid cycles
            if depth_up is not None and len(line_ids) - 1 >= depth_up:
                break
            line_ids.append(next_parent)
            current = next_parent

        included_ids = set(line_ids)

        # Optionally add descendants of the focal person (full subtree)
        if mode == 'subtree':
            queue = [(focal_id, 0)]
            while queue:
                pid, d = queue.pop(0)
                if depth_down is not None and d >= depth_down:
                    continue
                for child_id in parent_to_children.get(pid, []):
                    if child_id not in included_ids:
                        included_ids.add(child_id)
                    queue.append((child_id, d + 1))

        # Optionally bring in spouses of anyone included to keep cards coherent
        if include_spouses:
            for r in rels_qs:
                if r.relationship_type != Relationship.Type.SPOUSE:
                    continue
                if r.person1_id in included_ids or r.person2_id in included_ids:
                    included_ids.add(r.person1_id)
                    included_ids.add(r.person2_id)

        persons_out = [persons_by_id[pid] for pid in included_ids if pid in persons_by_id]
        rels_out = [
            r for r in rels_qs
            if r.person1_id in included_ids and r.person2_id in included_ids
        ]

        data = FamilyTreeSerializer(
            instance={
                'persons': persons_out,
                'relationships': rels_out,
            },
            context={'request': request},
        ).data

        return Response({
            'family_id': family_id,
            'focal_person_id': focal_id,
            'line': line,
            'mode': mode,
            'include_spouses': include_spouses,
            'depth_up': depth_up,
            'depth_down': depth_down,
            **data
        })


class FamilyLineCreateSpaceAPIView(APIView):
    """
    Create a new FamilySpace seeded from a maternal/paternal line export.

    POST /api/families/{family_id}/export/line/create-space/
    Body (JSON):
      {
        "name": "Smith Maternal Line",
        "description": "Branch seeded from Alice (maternal)",
        "person_id": 123,
        "line": "maternal|paternal",
        "mode": "line|subtree",
        "include_spouses": true,
        "parent_hint_id": 999,
        "depth_up": 3,
        "depth_down": 2
      }

    Only OWNER/ADMIN/EDITOR can create the new space. The caller is added as OWNER
    of the new space. Persons and relationships in the filtered set are copied
    into the new FamilySpace, preserving linked_user and photos.
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]

    def post(self, request, family_id):
        family = get_object_or_404(FamilySpace, id=family_id)
        membership = Membership.objects.filter(user=request.user, family=family).first()
        if not membership:
            return Response({'detail': 'Not a member'}, status=status.HTTP_403_FORBIDDEN)
        if membership.role not in ['OWNER', 'ADMIN', 'EDITOR']:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # Params from body (fallback to query params)
        data = request.data or {}
        q = request.query_params
        person_id = data.get('person_id') or q.get('person_id') or membership.linked_person_id
        line = (data.get('line') or q.get('line') or 'maternal').lower()
        mode = (data.get('mode') or q.get('mode') or 'subtree').lower()
        include_spouses = data.get('include_spouses', q.get('include_spouses', '1'))
        parent_hint_id = data.get('parent_hint_id') or q.get('parent_hint_id')
        depth_up = data.get('depth_up') or q.get('depth_up')
        depth_down = data.get('depth_down') or q.get('depth_down')

        def to_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        focal_id = to_int(person_id)
        if not focal_id:
            return Response({'detail': 'person_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if line not in ['maternal', 'paternal']:
            return Response({'detail': 'line must be maternal or paternal'}, status=status.HTTP_400_BAD_REQUEST)
        if mode not in ['line', 'subtree']:
            return Response({'detail': 'mode must be line or subtree'}, status=status.HTTP_400_BAD_REQUEST)
        include_spouses = (str(include_spouses) or '1') not in ['0', 'false', 'False']
        depth_up = to_int(depth_up)
        depth_down = to_int(depth_down)
        parent_hint_id = to_int(parent_hint_id)
        target_gender = Person.Gender.FEMALE if line == 'maternal' else Person.Gender.MALE

        persons_qs = Person.objects.filter(family=family, is_deleted=False)
        persons_by_id = {p.id: p for p in persons_qs}
        if focal_id not in persons_by_id:
            return Response({'detail': 'person not found in this family'}, status=status.HTTP_404_NOT_FOUND)

        rels_qs = Relationship.objects.filter(
            family=family,
            is_deleted=False,
            relationship_type__in=[Relationship.Type.PARENT_CHILD, Relationship.Type.SPOUSE]
        ).select_related('person1', 'person2')

        child_to_parents = {}
        parent_to_children = {}
        spouse_links = []
        for r in rels_qs:
            if r.relationship_type == Relationship.Type.PARENT_CHILD:
                child_to_parents.setdefault(r.person2_id, []).append(r.person1_id)
                parent_to_children.setdefault(r.person1_id, []).append(r.person2_id)
            elif r.relationship_type == Relationship.Type.SPOUSE:
                spouse_links.append((r.person1_id, r.person2_id))

        line_ids = [focal_id]
        current = focal_id
        while True:
            parents = child_to_parents.get(current, [])
            gender_matches = [pid for pid in parents if pid in persons_by_id and persons_by_id[pid].gender == target_gender]
            if parent_hint_id and current == focal_id and parent_hint_id in gender_matches:
                next_parent = parent_hint_id
            else:
                def sort_key(pid):
                    p = persons_by_id.get(pid)
                    byear = p.birth_date.year if (p and p.birth_date) else 9999
                    return (byear, pid)
                gender_matches = sorted(gender_matches, key=sort_key)
                next_parent = gender_matches[0] if gender_matches else None
            if not next_parent:
                break
            if next_parent in line_ids:
                break
            if depth_up is not None and len(line_ids) - 1 >= depth_up:
                break
            line_ids.append(next_parent)
            current = next_parent

        included_ids = set(line_ids)

        if mode == 'subtree':
            queue = [(focal_id, 0)]
            while queue:
                pid, d = queue.pop(0)
                if depth_down is not None and d >= depth_down:
                    continue
                for child_id in parent_to_children.get(pid, []):
                    if child_id not in included_ids:
                        included_ids.add(child_id)
                    queue.append((child_id, d + 1))

        if include_spouses:
            for a, b in spouse_links:
                if a in included_ids or b in included_ids:
                    included_ids.add(a)
                    included_ids.add(b)

        persons_to_copy = [persons_by_id[pid] for pid in included_ids if pid in persons_by_id]
        rels_to_copy = [r for r in rels_qs if r.person1_id in included_ids and r.person2_id in included_ids]

        new_name = data.get('name') or f"{line.title()} line of {request.user.get_full_name() or request.user.username}"
        new_description = data.get('description', '')
        new_family = FamilySpace.objects.create(
            name=new_name[:120],
            description=new_description,
            created_by=request.user,
        )
        Membership.objects.create(
            family=new_family,
            user=request.user,
            role=Membership.Role.OWNER,
        )

        id_map = {}
        for src in persons_to_copy:
            new_person = Person.objects.create(
                family=new_family,
                first_name=src.first_name,
                last_name=src.last_name,
                maiden_name=src.maiden_name,
                gender=src.gender,
                birth_date=src.birth_date,
                birth_date_qualifier=src.birth_date_qualifier,
                death_date=src.death_date,
                death_date_qualifier=src.death_date_qualifier,
                birth_place=src.birth_place,
                death_place=src.death_place,
                bio=src.bio,
                photo=src.photo,
                linked_user=src.linked_user,
                is_private=src.is_private,
                created_by=request.user,
            )
            id_map[src.id] = new_person

        for r in rels_to_copy:
            p1 = id_map.get(r.person1_id)
            p2 = id_map.get(r.person2_id)
            if not (p1 and p2):
                continue
            Relationship.objects.create(
                family=new_family,
                person1=p1,
                person2=p2,
                relationship_type=r.relationship_type,
                start_date=r.start_date,
                end_date=r.end_date,
                notes=r.notes,
            )

        return Response({
            'detail': 'Family space created',
            'new_family_id': new_family.id,
            'persons_copied': len(id_map),
            'relationships_copied': Relationship.objects.filter(family=new_family).count()
        }, status=status.HTTP_201_CREATED)

class SelfLinkAPIView(APIView):
    """
    Allow a logged-in family member to create/link their own Person record and center the tree on them.
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]

    def post(self, request, family_id):
        family = get_object_or_404(FamilySpace, id=family_id)
        membership = Membership.objects.filter(user=request.user, family=family).first()
        if not membership:
            return Response({'detail': 'Not a member'}, status=status.HTTP_403_FORBIDDEN)

        if membership.linked_person:
            person = membership.linked_person
            return Response(PersonDetailSerializer(person).data)

        # If there's already a Person linked to this user in the family, reuse it
        existing = Person.objects.filter(family=family, linked_user=request.user, is_deleted=False).first()
        if existing:
            membership.linked_person = existing
            membership.save(update_fields=["linked_person"])
            return Response(PersonDetailSerializer(existing).data)

        # Otherwise create a new person from provided minimal fields
        serializer = PersonCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        person = serializer.save(family=family, created_by=request.user)
        person.linked_user = request.user
        person.save(update_fields=["linked_user"])

        membership.linked_person = person
        membership.save(update_fields=["linked_person"])

        return Response(PersonDetailSerializer(person).data, status=status.HTTP_201_CREATED)


class PendingPersonChangeAPIView(APIView):
    """
    List and approve/reject pending person changes.
    """
    permission_classes = [permissions.IsAuthenticated, IsFamilyMember]

    def get(self, request, family_id):
        membership = Membership.objects.filter(user=request.user, family_id=family_id).first()
        if not membership or membership.role not in ['OWNER', 'ADMIN', 'EDITOR']:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        pending = PendingPersonChange.objects.filter(family_id=family_id, status=PendingPersonChange.Status.PENDING)
        serializer = PendingPersonChangeSerializer(pending, many=True)
        return Response(serializer.data)

    def post(self, request, family_id):
        """
        Approve or reject a pending change.
        Body: { "change_id": int, "action": "APPROVE"|"REJECT", "notes": "..." }
        """
        membership = Membership.objects.filter(user=request.user, family_id=family_id).first()
        if not membership or membership.role not in ['OWNER', 'ADMIN', 'EDITOR']:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        change_id = request.data.get('change_id')
        decision = (request.data.get('action') or '').upper()
        notes = request.data.get('notes', '')

        change = get_object_or_404(PendingPersonChange, id=change_id, family_id=family_id)
        if change.status != PendingPersonChange.Status.PENDING:
            return Response({'detail': 'Already reviewed'}, status=status.HTTP_400_BAD_REQUEST)

        if decision == 'REJECT':
            change.status = PendingPersonChange.Status.REJECTED
            change.review_notes = notes
            change.reviewed_by = request.user
            change.reviewed_at = timezone.now()
            change.save()
            return Response({'detail': 'Rejected'})

        if decision != 'APPROVE':
            return Response({'detail': 'action must be APPROVE or REJECT'}, status=status.HTTP_400_BAD_REQUEST)

        # Apply change
        if change.action == PendingPersonChange.Action.CREATE:
            serializer = PersonCreateUpdateSerializer(data=change.payload)
            serializer.is_valid(raise_exception=True)
            serializer.save(family_id=family_id, created_by=change.created_by or request.user)
        elif change.action == PendingPersonChange.Action.UPDATE:
            if not change.person:
                return Response({'detail': 'No target person for update'}, status=status.HTTP_400_BAD_REQUEST)
            serializer = PersonCreateUpdateSerializer(change.person, data=change.payload, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif change.action == PendingPersonChange.Action.DELETE:
            if change.person:
                change.person.is_deleted = True
                change.person.save()

        change.status = PendingPersonChange.Status.APPROVED
        change.review_notes = notes
        change.reviewed_by = request.user
        change.reviewed_at = timezone.now()
        change.save()

        return Response({'detail': 'Approved and applied'})


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
