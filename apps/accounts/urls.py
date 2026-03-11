# apps/users/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    VerifyEmailView,
    ProfileView,
    PublicProfileView,
    DeleteAccountView,
    UserStatsView,
    UserSearchView,
    UserListView,
)

urlpatterns = [
    # ============ AUTH ============
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('auth/profile/', ProfileView.as_view(), name='profile'),
    path('auth/delete-account/', DeleteAccountView.as_view(), name='delete-account'),

    # ============ USERS ============
    path('users/', UserSearchView.as_view(), name='user-search'),
    path('users/list/', UserListView.as_view(), name='user-list'),
    path('users/<str:username>/', PublicProfileView.as_view(), name='public-profile'),

    # ============ STATS ============
    path('stats/', UserStatsView.as_view(), name='user-stats'),
]