# apps/venues/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VenueViewSet,
    UserRatingsView,
    PublicUserRatingsView,
)

router = DefaultRouter()
router.register(r'venues', VenueViewSet, basename='venue')

urlpatterns = [
    path('', include(router.urls)),
    # Kullanıcının kendi rating'leri (giriş yapmış)
    path('my-ratings/', UserRatingsView.as_view(), name='my-ratings'),
    # Herhangi bir kullanıcının rating'leri (public)
    path('users/<str:username>/ratings/', PublicUserRatingsView.as_view(), name='user-ratings'),
]