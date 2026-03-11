from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ContributionViewSet, VenueReportViewSet

router = DefaultRouter()
router.register(r'contributions', ContributionViewSet, basename='contribution')
router.register(r'reports', VenueReportViewSet, basename='report')

venue_view = ContributionViewSet.as_view({'post': 'create_venue'})
venue_edit_view = ContributionViewSet.as_view({'post': 'edit_venue'})
venue_add_category_view = ContributionViewSet.as_view({'post': 'add_category_to_venue'})

urlpatterns = [
    # Manual venue contribution URLs (router can't handle regex params in detail=False actions)
    path('contributions/venue/', venue_view),
    path('contributions/venue/<int:venue_id>/edit/', venue_edit_view),
    path('contributions/venue/<int:venue_id>/add-category/', venue_add_category_view),
    path('', include(router.urls)),
]