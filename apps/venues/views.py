# apps/venues/views.py

from rest_framework import viewsets, filters, permissions, status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from django.db.models import Q, Avg
from .models import Venue, VenueCategory, VenueRating
from .serializers import (
    VenueListSerializer, 
    VenueDetailSerializer, 
    VenueMapSerializer,
    VenueRatingSerializer,
    VenueRatingCreateSerializer
)


class VenuePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'


class VenueViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'city', 'country']
    ordering_fields = ['created_at', 'name']
    lookup_field = 'slug'
    pagination_class = VenuePagination

    def get_base_queryset(self):
        """Temel queryset - approved ve active venue'lar"""
        return Venue.objects.filter(is_approved=True, is_active=True)

    def apply_filters(self, queryset, request):
        """Ortak filtreleri uygula"""
        category = request.query_params.get('category')
        city = request.query_params.get('city')
        country = request.query_params.get('country')
        bbox = request.query_params.get('bbox')
        min_rating = request.query_params.get('min_rating')
        has_ratings = request.query_params.get('has_ratings')

        if category:
            queryset = queryset.filter(
                venue_categories__category__slug=category,
                venue_categories__is_approved=True
            )

        if city:
            queryset = queryset.filter(city__icontains=city)

        if country:
            queryset = queryset.filter(country__icontains=country)

        if bbox:
            try:
                min_lng, min_lat, max_lng, max_lat = map(float, bbox.split(','))
                queryset = queryset.filter(
                    latitude__gte=min_lat, latitude__lte=max_lat,
                    longitude__gte=min_lng, longitude__lte=max_lng,
                    latitude__isnull=False,
                    longitude__isnull=False,
                )
            except (ValueError, TypeError):
                pass

        if min_rating:
            try:
                min_val = float(min_rating)
                queryset = queryset.annotate(
                    avg_rating=Avg('ratings__score')
                ).filter(avg_rating__gte=min_val)
            except (ValueError, TypeError):
                pass

        if has_ratings == 'true':
            queryset = queryset.filter(ratings__isnull=False)

        # Field filters
        for key, value in request.query_params.items():
            if key.startswith('field__') and value:
                field_name = key[7:]  # "field__" prefix'ini kaldır
                
                if value.lower() in ('true', 'false'):
                    queryset = queryset.filter(
                        venue_categories__field_values__field__name=field_name,
                        venue_categories__field_values__value__iexact=value,
                    )
                elif ',' in value:
                    q = Q()
                    for v in value.split(','):
                        v = v.strip()
                        if v:
                            q |= Q(
                                venue_categories__field_values__field__name=field_name,
                                venue_categories__field_values__value__icontains=v,
                            )
                    if q:
                        queryset = queryset.filter(q)
                else:
                    queryset = queryset.filter(
                        venue_categories__field_values__field__name=field_name,
                        venue_categories__field_values__value__icontains=value,
                    )

        return queryset.distinct()

    def get_queryset(self):
        queryset = self.get_base_queryset()
        queryset = self.apply_filters(queryset, self.request)

        if self.action == 'list':
            return queryset.prefetch_related('venue_categories__category')

        # ── retrieve için genişletilmiş prefetch ──────────────────────────
        # nearby_venues / related_venues, serializer içinde Venue.objects
        # sorgusu yapar; bu queryset o sorgulardan bağımsız.
        # Ancak VenueNearbySerializer.get_primary_category_slug çağrısı
        # her nearby/related venue için venue_categories'e gider.
        # Bunu önlemek için Prefetch nesnesi kullanılabilir, ama
        # serializer kendi sub-queryset'ini yönetiyor — şimdilik yeterli.
        return queryset.prefetch_related(
            'venue_categories__category',
            'venue_categories__field_values__field',
            'venue_categories__field_values__field__choices',
            'ratings',
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VenueDetailSerializer
        if self.request.query_params.get('bbox'):
            return VenueMapSerializer
        return VenueListSerializer

    def list(self, request, *args, **kwargs):
        if request.query_params.get('count_only') == '1':
            return Response({'count': self.get_queryset().count()})

        if request.query_params.get('bbox'):
            self.pagination_class = None

        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        venue_slug = self.kwargs.get('slug')
        instance = self.get_queryset().filter(slug=venue_slug).first()

        if not instance:
            return Response(
                {"detail": "Venue not found or pending approval."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(instance)
        data = dict(serializer.data)

        # can_edit
        can_edit = False
        if request.user.is_authenticated:
            from apps.categories.models import Category
            category_slugs = [vc['category_slug'] for vc in data.get('categories', [])]
            for slug in category_slugs:
                try:
                    cat = Category.objects.get(slug=slug)
                    if cat.can_moderate(request.user):
                        can_edit = True
                        break
                except Category.DoesNotExist:
                    pass

        data['can_edit'] = can_edit
        
        # Kullanıcının bu mekana verdiği puan
        if request.user.is_authenticated:
            data['user_rating'] = instance.get_user_rating(request.user)
        else:
            data['user_rating'] = None
            
        return Response(data)

    # ============ MAP MARKERS - OPTIMIZED ============

    @action(detail=False, methods=['get'], url_path='map-markers')
    def map_markers(self, request):
        """
        Harita için minimal venue verisi.
        Sadece id, slug, name, latitude, longitude döner.
        Popup verisi YOK - çok hızlı!
        """
        queryset = self.get_base_queryset().filter(
            latitude__isnull=False,
            longitude__isnull=False
        )
        
        # Filtreleri uygula
        queryset = self.apply_filters(queryset, request)
        
        # Sadece gerekli alanları seç - VALUES ile çok hızlı
        markers = queryset.values(
            'id', 'slug', 'name', 'latitude', 'longitude'
        )[:3000]  # Max 3000 marker

        return Response(list(markers))

    # ============ CATEGORY ACTIONS ============

    @action(
        detail=True,
        methods=['post'],
        url_path='add-category',
        permission_classes=[permissions.IsAuthenticated],
    )
    def add_category(self, request, slug=None):
        """Venue'ya yeni kategori ekle"""
        venue = Venue.objects.filter(slug=slug).first()
        if not venue:
            return Response({'detail': 'Venue not found.'}, status=status.HTTP_404_NOT_FOUND)

        category_slug = request.data.get('category')
        if not category_slug:
            return Response({'detail': 'Category slug required.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.categories.models import Category
        try:
            category = Category.objects.get(slug=category_slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)

        vc, created = VenueCategory.objects.get_or_create(
            venue=venue,
            category=category,
            defaults={'is_approved': False},
        )

        if not created:
            return Response(
                {'detail': 'This venue is already in that category.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {'detail': 'Category added. Pending approval.', 'venue_category_id': vc.id},
            status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=['delete'],
        url_path='delete',
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_venue(self, request, slug=None):
        venue = Venue.objects.filter(slug=slug).first()
        if not venue:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.categories.models import Category
        
        can_delete = False
        for vc in venue.venue_categories.select_related('category'):
            if vc.category.can_moderate(request.user):
                can_delete = True
                break

        if not can_delete:
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        venue.delete()
        return Response({'detail': 'Deleted.'}, status=status.HTTP_204_NO_CONTENT)

    # ============ RATING ACTIONS ============

    @action(
        detail=True,
        methods=['get'],
        url_path='ratings',
        permission_classes=[permissions.AllowAny],
    )
    def get_ratings(self, request, slug=None):
        """Venue'nun tüm rating'lerini getir"""
        venue = Venue.objects.filter(slug=slug, is_approved=True, is_active=True).first()
        if not venue:
            return Response({'detail': 'Venue not found.'}, status=status.HTTP_404_NOT_FOUND)

        ratings = venue.ratings.filter(is_visible=True).select_related('user').order_by('-created_at')
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = ratings.count()
        ratings_page = ratings[start:end]
        
        serializer = VenueRatingSerializer(ratings_page, many=True)
        
        return Response({
            'count': total_count,
            'average_rating': venue.average_rating,
            'rating_count': venue.rating_count,
            'breakdown': venue.get_rating_breakdown(),
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 1,
            'results': serializer.data
        })

    @action(
        detail=True,
        methods=['post'],
        url_path='rate',
        permission_classes=[permissions.IsAuthenticated],
    )
    def rate_venue(self, request, slug=None):
        """Venue'ya puan ver veya güncelle"""
        venue = Venue.objects.filter(slug=slug, is_approved=True, is_active=True).first()
        if not venue:
            return Response({'detail': 'Venue not found.'}, status=status.HTTP_404_NOT_FOUND)

        score = request.data.get('score')
        comment = request.data.get('comment', '')

        if score is None:
            return Response({'detail': 'Score is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            score = int(score)
            if score < 1 or score > 5:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({'detail': 'Score must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)

        rating, created = VenueRating.objects.update_or_create(
            venue=venue,
            user=request.user,
            defaults={
                'score': score,
                'comment': comment[:500] if comment else '',
            }
        )

        return Response({
            'detail': 'Rating submitted.' if created else 'Rating updated.',
            'rating': VenueRatingSerializer(rating).data,
            'average_rating': venue.average_rating,
            'rating_count': venue.rating_count,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['delete'],
        url_path='rate/delete',
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_rating(self, request, slug=None):
        """Kullanıcının kendi rating'ini sil"""
        venue = Venue.objects.filter(slug=slug).first()
        if not venue:
            return Response({'detail': 'Venue not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            rating = VenueRating.objects.get(venue=venue, user=request.user)
            rating.delete()
            return Response({
                'detail': 'Rating deleted.',
                'average_rating': venue.average_rating,
                'rating_count': venue.rating_count,
            }, status=status.HTTP_200_OK)
        except VenueRating.DoesNotExist:
            return Response({'detail': 'You have not rated this venue.'}, status=status.HTTP_404_NOT_FOUND)


# ============ STANDALONE RATING VIEWS ============

class UserRatingsView(APIView):
    """Kullanıcının verdiği tüm puanları listele"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ratings = request.user.venue_ratings.filter(
            is_visible=True
        ).select_related('venue').order_by('-created_at')
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = ratings.count()
        ratings_page = ratings[start:end]
        
        data = []
        for r in ratings_page:
            data.append({
                'id': r.id,
                'score': r.score,
                'comment': r.comment,
                'created_at': r.created_at.isoformat(),
                'updated_at': r.updated_at.isoformat(),
                'venue': {
                    'id': r.venue.id,
                    'name': r.venue.name,
                    'slug': r.venue.slug,
                    'city': r.venue.city,
                    'country': r.venue.country,
                }
            })
        
        avg = request.user.venue_ratings.filter(is_visible=True).aggregate(avg=Avg('score'))
        
        return Response({
            'count': total_count,
            'average_rating_given': round(avg['avg'], 1) if avg['avg'] else None,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 1,
            'results': data
        })


class PublicUserRatingsView(APIView):
    """Herhangi bir kullanıcının verdiği puanları görüntüle (public)"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, username):
        from django.contrib.auth.models import User
        
        try:
            target_user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        ratings = target_user.venue_ratings.filter(
            is_visible=True
        ).select_related('venue').order_by('-created_at')
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = ratings.count()
        ratings_page = ratings[start:end]
        
        data = []
        for r in ratings_page:
            data.append({
                'id': r.id,
                'score': r.score,
                'comment': r.comment,
                'created_at': r.created_at.isoformat(),
                'venue': {
                    'id': r.venue.id,
                    'name': r.venue.name,
                    'slug': r.venue.slug,
                    'city': r.venue.city,
                }
            })
        
        avg = target_user.venue_ratings.filter(is_visible=True).aggregate(avg=Avg('score'))
        
        return Response({
            'username': username,
            'count': total_count,
            'average_rating_given': round(avg['avg'], 1) if avg['avg'] else None,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 1,
            'results': data
        })