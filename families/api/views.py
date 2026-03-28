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
from django.urls import reverse
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


BRANCH_LINE_CHOICES = ['maternal', 'paternal', 'person_side', 'spouse_side']


def _branch_to_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _branch_person_sort_key(pid, persons_by_id):
    person = persons_by_id.get(pid)
    birth_year = person.birth_date.year if (person and person.birth_date) else 9999
    last_name = (person.last_name or '').lower() if person else ''
    first_name = (person.first_name or '').lower() if person else ''
    return (birth_year, last_name, first_name, pid)


def _build_branch_context(family):
    persons_qs = Person.objects.filter(family=family, is_deleted=False)
    persons_by_id = {p.id: p for p in persons_qs}

    rels_qs = Relationship.objects.filter(
        family=family,
        is_deleted=False,
        relationship_type__in=[Relationship.Type.PARENT_CHILD, Relationship.Type.SPOUSE]
    ).select_related('person1', 'person2')

    child_to_parents = {}
    parent_to_children = {}
    spouse_links = []
    spouse_of = {}
    for rel in rels_qs:
        if rel.relationship_type == Relationship.Type.PARENT_CHILD:
            child_to_parents.setdefault(rel.person2_id, []).append(rel.person1_id)
            parent_to_children.setdefault(rel.person1_id, []).append(rel.person2_id)
        elif rel.relationship_type == Relationship.Type.SPOUSE:
            spouse_links.append((rel.person1_id, rel.person2_id))
            spouse_of.setdefault(rel.person1_id, []).append(rel.person2_id)
            spouse_of.setdefault(rel.person2_id, []).append(rel.person1_id)

    return {
        'persons_by_id': persons_by_id,
        'relationships': rels_qs,
        'child_to_parents': child_to_parents,
        'parent_to_children': parent_to_children,
        'spouse_links': spouse_links,
        'spouse_of': spouse_of,
    }


def _collect_gender_line_ids(focal_id, target_gender, child_to_parents, persons_by_id, depth_up=None, parent_hint_id=None):
    line_ids = [focal_id]
    current = focal_id
    while True:
        parents = child_to_parents.get(current, [])
        gender_matches = [
            pid for pid in parents
            if pid in persons_by_id and persons_by_id[pid].gender == target_gender
        ]

        if parent_hint_id and current == focal_id and parent_hint_id in gender_matches:
            next_parent = parent_hint_id
        else:
            gender_matches = sorted(gender_matches, key=lambda pid: _branch_person_sort_key(pid, persons_by_id))
            next_parent = gender_matches[0] if gender_matches else None

        if not next_parent:
            break
        if next_parent in line_ids:
            break
        if depth_up is not None and len(line_ids) - 1 >= depth_up:
            break
        line_ids.append(next_parent)
        current = next_parent

    return set(line_ids)


def _collect_full_side_ids(root_id, child_to_parents, persons_by_id, depth_up=None):
    included_ids = {root_id}
    queue = [(root_id, 0)]
    while queue:
        person_id, depth = queue.pop(0)
        if depth_up is not None and depth >= depth_up:
            continue
        parent_ids = sorted(
            set(child_to_parents.get(person_id, [])),
            key=lambda pid: _branch_person_sort_key(pid, persons_by_id),
        )
        for parent_id in parent_ids:
            if parent_id in included_ids:
                continue
            included_ids.add(parent_id)
            queue.append((parent_id, depth + 1))
    return included_ids


def _collect_descendant_ids(root_id, parent_to_children, spouse_of=None, depth_down=None):
    included_ids = set()
    seen_ids = {root_id}
    queue = [(root_id, 0)]
    while queue:
        person_id, depth = queue.pop(0)
        if depth_down is not None and depth >= depth_down:
            continue
        parent_ids = {person_id}
        if spouse_of:
            parent_ids.update(spouse_of.get(person_id, []))
        child_ids = set()
        for parent_id in parent_ids:
            child_ids.update(parent_to_children.get(parent_id, []))
        for child_id in sorted(child_ids):
            if child_id not in included_ids:
                included_ids.add(child_id)
            if child_id not in seen_ids:
                seen_ids.add(child_id)
                queue.append((child_id, depth + 1))
    return included_ids


def _resolve_spouse_branch_id(focal_id, spouse_of, persons_by_id, spouse_hint_id=None):
    spouse_ids = sorted(
        {pid for pid in spouse_of.get(focal_id, []) if pid in persons_by_id},
        key=lambda pid: _branch_person_sort_key(pid, persons_by_id),
    )
    if spouse_hint_id is not None and spouse_hint_id not in spouse_ids:
        raise ValueError('spouse_id must belong to the selected focal person')
    if spouse_hint_id is not None:
        return spouse_hint_id
    return spouse_ids[0] if spouse_ids else None


def _build_family_branch_bundle(
    family,
    focal_id,
    line='maternal',
    mode='subtree',
    include_spouses=True,
    parent_hint_id=None,
    depth_up=None,
    depth_down=None,
    spouse_hint_id=None,
):
    if line not in BRANCH_LINE_CHOICES:
        raise ValueError('line must be maternal, paternal, person_side, or spouse_side')
    if mode not in ['line', 'subtree']:
        raise ValueError('mode must be line or subtree')

    context = _build_branch_context(family)
    persons_by_id = context['persons_by_id']
    rels_qs = context['relationships']
    child_to_parents = context['child_to_parents']
    parent_to_children = context['parent_to_children']
    spouse_links = context['spouse_links']
    spouse_of = context['spouse_of']

    if focal_id not in persons_by_id:
        raise LookupError('person not found in this family')

    branch_root_id = focal_id
    selected_spouse_id = None

    if line == 'maternal':
        included_ids = _collect_gender_line_ids(
            focal_id,
            Person.Gender.FEMALE,
            child_to_parents,
            persons_by_id,
            depth_up=depth_up,
            parent_hint_id=parent_hint_id,
        )
    elif line == 'paternal':
        included_ids = _collect_gender_line_ids(
            focal_id,
            Person.Gender.MALE,
            child_to_parents,
            persons_by_id,
            depth_up=depth_up,
            parent_hint_id=parent_hint_id,
        )
    else:
        if line == 'spouse_side':
            selected_spouse_id = _resolve_spouse_branch_id(
                focal_id,
                spouse_of,
                persons_by_id,
                spouse_hint_id=spouse_hint_id,
            )
            if not selected_spouse_id:
                raise ValueError('selected person has no spouse in this tree')
            branch_root_id = selected_spouse_id
        included_ids = _collect_full_side_ids(
            branch_root_id,
            child_to_parents,
            persons_by_id,
            depth_up=depth_up,
        )

    if mode == 'subtree':
        included_ids.update(
            _collect_descendant_ids(
                branch_root_id,
                parent_to_children,
                spouse_of=spouse_of,
                depth_down=depth_down,
            )
        )

    if include_spouses:
        for person1_id, person2_id in spouse_links:
            if person1_id in included_ids or person2_id in included_ids:
                included_ids.add(person1_id)
                included_ids.add(person2_id)

    persons_out = [persons_by_id[pid] for pid in included_ids if pid in persons_by_id]
    rels_out = [
        rel for rel in rels_qs
        if rel.person1_id in included_ids and rel.person2_id in included_ids
    ]

    return {
        'persons': persons_out,
        'relationships': rels_out,
        'branch_root_id': branch_root_id,
        'selected_spouse_id': selected_spouse_id,
    }


def _default_branch_space_name(line, request_user):
    line_label = {
        'maternal': 'Maternal',
        'paternal': 'Paternal',
        'person_side': 'Person Side',
        'spouse_side': 'Spouse Side',
    }.get(line, 'Branch')
    display_name = request_user.get_full_name() or request_user.username
    return f"{line_label} of {display_name}"


class FamilyLineExportAPIView(APIView):
    """
    Export a person's branch as a mini tree (JSON).

    GET /api/families/{family_id}/export/line/?person_id=123&line=maternal|paternal|person_side|spouse_side&mode=line|subtree&include_spouses=0|1&parent_hint_id=999&spouse_id=555&depth_up=3&depth_down=2

    - line: required, which branch rule to follow (defaults to maternal).
    - person_id: defaults to the caller's linked person (if set).
    - mode:
        * line     -> just the direct ancestors + root person for the chosen branch
        * subtree  -> chosen branch ancestors + all descendants of the branch root
                      (useful to seed a new space)
    - include_spouses: if truthy, adds spouses of included people to make cards coherent.
    - parent_hint_id: optional disambiguator when multiple mothers/fathers exist; only applied to the first hop for maternal/paternal exports.
    - spouse_id: optional spouse picker when exporting spouse_side.
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
        focal_id = _branch_to_int(person_id)
        if not focal_id:
            return Response({'detail': 'person_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        line = (request.query_params.get('line') or 'maternal').lower()
        mode = (request.query_params.get('mode') or 'subtree').lower()
        include_spouses = (request.query_params.get('include_spouses') or '1') not in ['0', 'false', 'False']
        depth_up = _branch_to_int(request.query_params.get('depth_up'))
        depth_down = _branch_to_int(request.query_params.get('depth_down'))
        parent_hint_id = _branch_to_int(request.query_params.get('parent_hint_id'))
        spouse_hint_id = _branch_to_int(request.query_params.get('spouse_id'))

        try:
            bundle = _build_family_branch_bundle(
                family,
                focal_id,
                line=line,
                mode=mode,
                include_spouses=include_spouses,
                parent_hint_id=parent_hint_id,
                depth_up=depth_up,
                depth_down=depth_down,
                spouse_hint_id=spouse_hint_id,
            )
        except LookupError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = FamilyTreeSerializer(
            instance={
                'persons': bundle['persons'],
                'relationships': bundle['relationships'],
            },
            context={'request': request},
        ).data

        return Response({
            'family_id': family_id,
            'focal_person_id': focal_id,
            'branch_root_id': bundle['branch_root_id'],
            'selected_spouse_id': bundle['selected_spouse_id'],
            'line': line,
            'mode': mode,
            'include_spouses': include_spouses,
            'depth_up': depth_up,
            'depth_down': depth_down,
            **data
        })


class FamilyLineCreateSpaceAPIView(APIView):
    """
    Create a new FamilySpace seeded from a filtered branch export.

    POST /api/families/{family_id}/export/line/create-space/
    Body (JSON):
      {
        "name": "Smith Maternal Line",
        "description": "Branch seeded from Alice",
        "person_id": 123,
        "line": "maternal|paternal|person_side|spouse_side",
        "mode": "line|subtree",
        "include_spouses": true,
        "spouse_id": 555,
        "parent_hint_id": 999,
        "depth_up": 3,
        "depth_down": 2
      }

    Only OWNER/ADMIN/EDITOR can create the new space. The caller is added as OWNER
    of the new space. Persons and relationships in the filtered set are copied
    into the new FamilySpace, preserving photos and linking the new membership
    back to the copied focal person when possible.
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

        focal_id = _branch_to_int(person_id)
        if not focal_id:
            return Response({'detail': 'person_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        include_spouses = (str(include_spouses) or '1') not in ['0', 'false', 'False']
        depth_up = _branch_to_int(depth_up)
        depth_down = _branch_to_int(depth_down)
        parent_hint_id = _branch_to_int(parent_hint_id)
        spouse_hint_id = _branch_to_int(data.get('spouse_id') or q.get('spouse_id'))

        try:
            bundle = _build_family_branch_bundle(
                family,
                focal_id,
                line=line,
                mode=mode,
                include_spouses=include_spouses,
                parent_hint_id=parent_hint_id,
                depth_up=depth_up,
                depth_down=depth_down,
                spouse_hint_id=spouse_hint_id,
            )
        except LookupError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        persons_to_copy = bundle['persons']
        rels_to_copy = bundle['relationships']

        new_name = data.get('name') or _default_branch_space_name(line, request.user)
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
        new_membership = Membership.objects.get(family=new_family, user=request.user)

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
                linked_user=None,
                is_private=src.is_private,
                created_by=request.user,
            )
            id_map[src.id] = new_person

            if src.linked_user_id == request.user.id and not new_membership.linked_person_id:
                new_membership.linked_person = new_person

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

        if new_membership.linked_person_id:
            new_membership.save(update_fields=["linked_person"])

        return Response({
            'detail': 'Family space created',
            'new_family_id': new_family.id,
            'new_family_url': reverse("families:family_detail", kwargs={"family_id": new_family.id}),
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
