# apps/users/views.py

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.utils.decorators import method_decorator
from django.db.models import Q, Count, Avg
from django_ratelimit.decorators import ratelimit
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.signals import user_login_failed, user_logged_in
from axes.handlers.proxy import AxesProxyHandler
from .serializers import RegisterSerializer, UserProfileSerializer
from .models import EmailVerificationToken, UserProfile
from apps.contributions.models import Contribution
from apps.venues.models import Venue, VenueContributor, VenueRating


@method_decorator(ratelimit(key='ip', rate='5/h', method='POST', block=True), name='post')
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        token_obj = EmailVerificationToken.objects.create(user=user)
        verify_url = f"https://mapedia.org/verify-email?token={token_obj.token}"
        send_mail(
            subject="Verify your Mapedia account",
            message=(
                f"Hi {user.username},\n\n"
                f"Please verify your email address by clicking the link below:\n\n"
                f"{verify_url}\n\n"
                f"If you didn't create an account, you can ignore this email.\n\n"
                f"— Mapedia Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


@method_decorator(ratelimit(key='ip', rate='10/h', method='GET', block=True), name='get')
class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({'detail': 'Token required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_obj = EmailVerificationToken.objects.get(token=token)
        except EmailVerificationToken.DoesNotExist:
            return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)

        user = token_obj.user
        user.is_active = True
        user.save()
        token_obj.delete()

        return Response({'detail': 'Email verified successfully. You can now log in.'})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if AxesProxyHandler.is_allowed(request) == False:
            return Response(
                {'detail': 'Too many failed login attempts. Please try again later.'},
                status=status.HTTP_403_FORBIDDEN
            )

        user = authenticate(request=request, username=username, password=password)

        if user is None:
            user_login_failed.send(
                sender=__name__,
                credentials={'username': username},
                request=request
            )
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {'detail': 'Please verify your email before logging in.'},
                status=status.HTTP_403_FORBIDDEN
            )

        user_logged_in.send(
            sender=__name__,
            user=user,
            request=request
        )

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'username': user.username,
                'email': user.email
            }
        })


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user_obj = request.user
        serializer = UserProfileSerializer(user_obj.profile)
        data = serializer.data
        data['id'] = user_obj.id
        data['username'] = user_obj.username
        data['email'] = user_obj.email
        data['date_joined'] = user_obj.date_joined

        # 1. Normal Katkılar
        contributions = Contribution.objects.filter(
            contributor=user_obj.profile
        ).select_related('venue').order_by('-created_at')
        
        # 2. Bot/İçe Aktarılan Katkılar
        imported_venues = VenueContributor.objects.filter(user=user_obj)
        
        data['contribution_count'] = contributions.count() + imported_venues.count()
        
        data['contributions'] = []
        for c in contributions[:100]:
            cat_slug = None
            if c.venue:
                first_vc = c.venue.venue_categories.select_related('category').first()
                if first_vc and first_vc.category:
                    cat_slug = first_vc.category.slug

            data['contributions'].append({
                'id': c.id,
                'type': c.contribution_type,
                'name': c.venue.name if c.venue else c.payload.get('name', ''),
                'status': c.status,
                'created_at': c.created_at.isoformat(),
                'venue_slug': c.venue.slug if c.venue else None,
                'category_slug': cat_slug,
            })

        from apps.categories.models import Category
        owned = Category.objects.filter(owner=user_obj, is_active=True)
        moderated = Category.objects.filter(moderators=user_obj, is_active=True).exclude(owner=user_obj)
        
        data['owned_categories'] = [
            {
                'id': c.id, 
                'name': c.name, 
                'slug': c.slug, 
                'icon': c.icon,
                'venue_count': c.venue_categories.filter(is_approved=True).count()
            }
            for c in owned
        ]
        data['moderated_categories'] = [
            {
                'id': c.id, 
                'name': c.name, 
                'slug': c.slug, 
                'icon': c.icon,
                'venue_count': c.venue_categories.filter(is_approved=True).count()
            }
            for c in moderated
        ]

        # Mekan ID'lerini birleştir
        approved_venue_ids = list(contributions.filter(
            status='approved',
            venue__isnull=False
        ).values_list('venue_id', flat=True).distinct())
        
        imported_venue_ids = list(imported_venues.values_list('venue_id', flat=True).distinct())
        all_venue_ids = list(set(approved_venue_ids + imported_venue_ids))
        
        venues = Venue.objects.filter(
            id__in=all_venue_ids, 
            is_approved=True
        ).prefetch_related('venue_categories__category').order_by('-id')[:100]
        
        data['my_venues'] = []
        for v in venues:
            first_vc = v.venue_categories.first()
            data['my_venues'].append({
                'id': v.id,
                'name': v.name,
                'slug': v.slug,
                'city': v.city,
                'country': v.country,
                'category_name': first_vc.category.name if first_vc and first_vc.category else '',
                'category_slug': first_vc.category.slug if first_vc and first_vc.category else '',
            })

        # ============ RATING İSTATİSTİKLERİ ============
        user_ratings = user_obj.venue_ratings.all()
        rating_avg = user_ratings.aggregate(avg=Avg('score'))
        
        data['ratings_given_count'] = user_ratings.count()
        data['average_rating_given'] = round(rating_avg['avg'], 1) if rating_avg['avg'] else None
        
        # Son 10 rating
        data['recent_ratings'] = []
        for r in user_ratings.select_related('venue').order_by('-created_at')[:10]:
            data['recent_ratings'].append({
                'id': r.id,
                'score': r.score,
                'comment': r.comment[:100] if r.comment else '',
                'created_at': r.created_at.isoformat(),
                'venue': {
                    'id': r.venue.id,
                    'name': r.venue.name,
                    'slug': r.venue.slug,
                }
            })
            
        return Response(data)

    def patch(self, request):
        profile = request.user.profile
        bio = request.data.get('bio')
        if bio is not None:
            profile.bio = bio
        if 'avatar' in request.FILES:
            avatar = request.FILES['avatar']
            if avatar.size > 2 * 1024 * 1024:
                return Response(
                    {'detail': 'Avatar too large. Max 2MB.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not avatar.content_type.startswith('image/'):
                return Response(
                    {'detail': 'Invalid file type.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            profile.avatar = avatar
        profile.save()
        return Response({'detail': 'Updated.'})


class PublicProfileView(APIView):
    """Herkese açık profil görüntüleme"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, username):
        try:
            target_user = User.objects.select_related('profile').get(username=username)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserProfileSerializer(target_user.profile)
        data = serializer.data
        data['id'] = target_user.id
        data['username'] = target_user.username
        data['date_joined'] = target_user.date_joined

        # 1. Normal Katkılar
        contributions = Contribution.objects.filter(
            contributor=target_user.profile
        ).select_related('venue').order_by('-created_at')
        
        # 2. Bot/İçe Aktarılan Katkılar
        imported_venues = VenueContributor.objects.filter(user=target_user)
        
        data['contribution_count'] = contributions.count() + imported_venues.count()

        data['contributions'] = []
        for c in contributions[:100]:
            cat_slug = None
            if c.venue:
                first_vc = c.venue.venue_categories.select_related('category').first()
                if first_vc and first_vc.category:
                    cat_slug = first_vc.category.slug

            data['contributions'].append({
                'id': c.id,
                'type': c.contribution_type,
                'name': c.venue.name if c.venue else c.payload.get('name', ''),
                'status': c.status,
                'created_at': c.created_at.isoformat(),
                'venue_slug': c.venue.slug if c.venue else None,
                'category_slug': cat_slug,
            })

        from apps.categories.models import Category
        owned = Category.objects.filter(owner=target_user, is_active=True)
        moderated = Category.objects.filter(moderators=target_user, is_active=True).exclude(owner=target_user)
        
        data['owned_categories'] = [
            {
                'id': c.id, 
                'name': c.name, 
                'slug': c.slug, 
                'icon': c.icon,
                'venue_count': c.venue_categories.filter(is_approved=True).count()
            }
            for c in owned
        ]
        data['moderated_categories'] = [
            {
                'id': c.id, 
                'name': c.name, 
                'slug': c.slug, 
                'icon': c.icon,
                'venue_count': c.venue_categories.filter(is_approved=True).count()
            }
            for c in moderated
        ]

        # Mekan ID'lerini birleştir
        approved_venue_ids = list(contributions.filter(
            status='approved',
            venue__isnull=False
        ).values_list('venue_id', flat=True).distinct())
        
        imported_venue_ids = list(imported_venues.values_list('venue_id', flat=True).distinct())
        all_venue_ids = list(set(approved_venue_ids + imported_venue_ids))

        venues = Venue.objects.filter(
            id__in=all_venue_ids, 
            is_approved=True
        ).prefetch_related('venue_categories__category').order_by('-id')[:100]

        data['my_venues'] = []
        for v in venues:
            first_vc = v.venue_categories.first()
            data['my_venues'].append({
                'id': v.id,
                'name': v.name,
                'slug': v.slug,
                'city': v.city,
                'country': v.country,
                'category_name': first_vc.category.name if first_vc and first_vc.category else '',
                'category_slug': first_vc.category.slug if first_vc and first_vc.category else '',
            })

        # ============ RATING İSTATİSTİKLERİ ============
        user_ratings = target_user.venue_ratings.filter(is_visible=True)
        rating_avg = user_ratings.aggregate(avg=Avg('score'))
        
        data['ratings_given_count'] = user_ratings.count()
        data['average_rating_given'] = round(rating_avg['avg'], 1) if rating_avg['avg'] else None
        
        # Son 10 rating (public)
        data['recent_ratings'] = []
        for r in user_ratings.select_related('venue').order_by('-created_at')[:10]:
            data['recent_ratings'].append({
                'id': r.id,
                'score': r.score,
                'comment': r.comment[:100] if r.comment else '',
                'created_at': r.created_at.isoformat(),
                'venue': {
                    'id': r.venue.id,
                    'name': r.venue.name,
                    'slug': r.venue.slug,
                }
            })

        return Response(data)


class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'detail': 'Account deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


class UserStatsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.venues.models import Venue, VenueRating
        from apps.categories.models import Category
        from apps.contributions.models import Contribution
        
        user_count = User.objects.filter(is_active=True).count()
        venue_count = Venue.objects.filter(is_approved=True, is_active=True).count()
        category_count = Category.objects.filter(is_active=True).count()
        rating_count = VenueRating.objects.filter(is_visible=True).count()
        contribution_count = Contribution.objects.filter(status='approved').count()
        
        return Response({
            'user_count': user_count,
            'venue_count': venue_count,
            'category_count': category_count,
            'rating_count': rating_count,
            'contribution_count': contribution_count,
        })


class UserSearchView(APIView):
    """Kullanıcı arama"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = request.query_params.get('search', '').strip()
        
        if len(query) < 2:
            return Response([])
        
        users = User.objects.filter(
            Q(username__icontains=query) | 
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query),
            is_active=True
        ).select_related('profile')[:10]
        
        result = []
        for user in users:
            contribution_count = 0
            try:
                contribution_count = Contribution.objects.filter(
                    contributor=user.profile
                ).count()
                contribution_count += VenueContributor.objects.filter(user=user).count()
            except:
                pass
            
            avatar_url = None
            try:
                if user.profile.avatar:
                    avatar_url = request.build_absolute_uri(user.profile.avatar.url)
            except:
                pass
            
            # Rating stats
            ratings_count = user.venue_ratings.count()
            
            result.append({
                'id': user.id,
                'username': user.username,
                'avatar': avatar_url,
                'contribution_count': contribution_count,
                'ratings_count': ratings_count,
                'is_trusted': getattr(user.profile, 'is_trusted', False) if hasattr(user, 'profile') else False,
                'date_joined': user.date_joined.isoformat(),
            })
        
        return Response(result)


class UserListView(APIView):
    """Tüm kullanıcıları listele (leaderboard)"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        ordering = request.query_params.get('ordering', '-date_joined')
        
        users = User.objects.filter(is_active=True).select_related('profile')
        
        if ordering == '-contribution_count':
            users = users.annotate(
                contrib_count=Count('profile__contributions')
            ).order_by('-contrib_count')
        elif ordering == 'contribution_count':
            users = users.annotate(
                contrib_count=Count('profile__contributions')
            ).order_by('contrib_count')
        elif ordering == '-ratings_count':
            users = users.annotate(
                ratings_count=Count('venue_ratings')
            ).order_by('-ratings_count')
        elif ordering in ['-date_joined', 'date_joined', '-username', 'username']:
            users = users.order_by(ordering)
        else:
            users = users.order_by('-date_joined')
        
        total_count = users.count()
        
        start = (page - 1) * page_size
        end = start + page_size
        users_page = users[start:end]
        
        result = []
        for user in users_page:
            contribution_count = 0
            try:
                contribution_count = Contribution.objects.filter(
                    contributor=user.profile
                ).count()
                contribution_count += VenueContributor.objects.filter(user=user).count()
            except:
                pass
            
            avatar_url = None
            try:
                if user.profile.avatar:
                    avatar_url = request.build_absolute_uri(user.profile.avatar.url)
            except:
                pass
            
            # Rating stats
            ratings_count = user.venue_ratings.count()
            avg_rating = user.venue_ratings.aggregate(avg=Avg('score'))
            
            result.append({
                'id': user.id,
                'username': user.username,
                'avatar': avatar_url,
                'contribution_count': contribution_count,
                'ratings_count': ratings_count,
                'average_rating_given': round(avg_rating['avg'], 1) if avg_rating['avg'] else None,
                'is_trusted': getattr(user.profile, 'is_trusted', False) if hasattr(user, 'profile') else False,
                'date_joined': user.date_joined.isoformat(),
            })
        
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': result
        })