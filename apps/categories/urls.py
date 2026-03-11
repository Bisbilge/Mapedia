from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = [
    path('', include(router.urls)),
    path(
        'categories/<slug:slug>/fields/<int:field_id>/edit/',
        CategoryViewSet.as_view({'patch': 'edit_field'}),
        name='category-edit-field'
    ),
    path(
        'categories/<slug:slug>/fields/<int:field_id>/delete/',
        CategoryViewSet.as_view({'delete': 'delete_field'}),
        name='category-delete-field'
    ),
]