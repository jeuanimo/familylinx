"""
Family Tree API URLs

REST Framework URL routing for the family tree API.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for viewsets
router = DefaultRouter()

# These URLs will be nested under /api/families/<family_id>/
# Persons: /api/families/<family_id>/persons/
# Relationships: /api/families/<family_id>/relationships/

app_name = 'families_api'

urlpatterns = [
    # Family tree data endpoint (D3.js format)
    path('families/<int:family_id>/tree/', views.FamilyTreeAPIView.as_view(), name='family_tree'),
    
    # Person search
    path('families/<int:family_id>/persons/search/', views.PersonSearchAPIView.as_view(), name='person_search'),
    
    # Person CRUD
    path('families/<int:family_id>/persons/', 
         views.PersonViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='person_list'),
    path('families/<int:family_id>/persons/<int:pk>/', 
         views.PersonViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), 
         name='person_detail'),
    path('families/<int:family_id>/persons/<int:pk>/add_parent/', 
         views.PersonViewSet.as_view({'post': 'add_parent'}), 
         name='person_add_parent'),
    path('families/<int:family_id>/persons/<int:pk>/add_spouse/', 
         views.PersonViewSet.as_view({'post': 'add_spouse'}), 
         name='person_add_spouse'),
    path('families/<int:family_id>/persons/<int:pk>/add_child/', 
         views.PersonViewSet.as_view({'post': 'add_child'}), 
         name='person_add_child'),
    
    # Relationship CRUD
    path('families/<int:family_id>/relationships/', 
         views.RelationshipViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='relationship_list'),
    path('families/<int:family_id>/relationships/<int:pk>/', 
         views.RelationshipViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'}), 
         name='relationship_detail'),
]
