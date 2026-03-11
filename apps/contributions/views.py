from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.db import models as django_models
from django_ratelimit.decorators import ratelimit
from .models import Contribution, VenueReport
from .serializers import VenueContributionSerializer, ContributionSerializer, VenueReportSerializer
from apps.venues.models import Venue, VenueCategory
from apps.categories.models import FieldValue, FieldDefinition
import re
from decimal import Decimal, ROUND_HALF_UP


class ContributionViewSet(viewsets.ViewSet):

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='pending')
    def pending(self, request):
        from apps.categories.models import Category

        if request.user.is_superuser:
            categories = Category.objects.filter(is_active=True)
        else:
            categories = Category.objects.filter(
                django_models.Q(owner=request.user) |
                django_models.Q(moderators=request.user)
            ).distinct()

        category_slug = request.query_params.get('category')

        if category_slug:
            try:
                category = categories.get(slug=category_slug)
            except Category.DoesNotExist:
                return Response({'detail': 'Forbidden.'}, status=403)

            contributions = Contribution.objects.filter(
                status='pending',
                payload__category=category_slug
            ).order_by('-created_at')

            data = []
            for c in contributions:
                data.append({
                    'id': c.id,
                    'contribution_type': c.contribution_type,
                    'payload': c.payload,
                    'status': c.status,
                    'contributor': c.contributor.user.username if c.contributor else 'anonymous',
                    'created_at': c.created_at.isoformat(),
                })
            return Response(data)

        data = []
        for cat in categories:
            pending_count = Contribution.objects.filter(
                status='pending',
                payload__category=cat.slug
            ).count()
            data.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'pending_count': pending_count,
                'is_owner': cat.owner == request.user,
            })
        return Response(data)

    @action(detail=False, methods=['get'], url_path='history')
    def history(self, request):
        """Get all contributions (pending, approved, rejected) for a category."""
        from apps.categories.models import Category

        category_slug = request.query_params.get('category')
        if not category_slug:
            return Response({'detail': 'category parameter required.'}, status=400)

        # Check permissions
        if request.user.is_superuser:
            categories = Category.objects.filter(is_active=True)
        else:
            categories = Category.objects.filter(
                django_models.Q(owner=request.user) |
                django_models.Q(moderators=request.user)
            ).distinct()

        try:
            category = categories.get(slug=category_slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Forbidden.'}, status=403)

        # Build queryset
        queryset = Contribution.objects.filter(
            payload__category=category_slug
        ).order_by('-created_at')

        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter and status_filter in ['pending', 'approved', 'rejected']:
            queryset = queryset.filter(status=status_filter)

        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size

        total_count = queryset.count()
        contributions = queryset[start:end]

        data = []
        for c in contributions:
            item = {
                'id': c.id,
                'contribution_type': c.contribution_type,
                'payload': c.payload,
                'status': c.status,
                'contributor': c.contributor.user.username if c.contributor else 'anonymous',
                'created_at': c.created_at.isoformat(),
                'moderated_at': c.moderated_at.isoformat() if c.moderated_at else None,
                'moderator': c.moderator.user.username if c.moderator else None,
                'moderation_note': c.moderation_note or '',
            }
            if c.venue:
                item['venue_id'] = c.venue.id
                item['venue_slug'] = c.venue.slug
            data.append(item)

        return Response({
            'count': total_count,
            'results': data,
        })

    @method_decorator(ratelimit(key='user', rate='20/d', method='POST', block=True))
    @action(detail=False, methods=['post'], url_path='venue')
    def create_venue(self, request):
        serializer = VenueContributionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Build payload with all fields including map_url
        payload = {
            'name': data['name'],
            'latitude': str(data.get('latitude', '') or ''),
            'longitude': str(data.get('longitude', '') or ''),
            'city': data.get('city', ''),
            'country': data.get('country', ''),
            'address': data.get('address', ''),
            'map_url': data.get('map_url', ''),
            'category': data['category'].slug,
            'field_values': data.get('field_values', {}),
        }

        contribution = Contribution.objects.create(
            contributor=request.user.profile,
            contribution_type='add_venue',
            payload=payload
        )

        if request.user.profile.is_trusted:
            self._apply_contribution(contribution)

        return Response(
            ContributionSerializer(contribution).data,
            status=status.HTTP_201_CREATED
        )

    @method_decorator(ratelimit(key='user', rate='20/d', method='POST', block=True))
    @action(detail=False, methods=['post'], url_path='venue/(?P<venue_id>[0-9]+)/edit')
    def edit_venue(self, request, venue_id=None):
        try:
            venue = Venue.objects.get(pk=venue_id, is_approved=True)
        except Venue.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)

        vc = venue.venue_categories.select_related('category').first()
        category_slug = request.data.get('category') or (vc.category.slug if vc else '')

        contribution = Contribution.objects.create(
            contributor=request.user.profile,
            contribution_type='edit_venue',
            venue=venue,
            payload={
                'venue_id': venue_id,
                'name': request.data.get('name', venue.name),
                'city': request.data.get('city', venue.city),
                'country': request.data.get('country', venue.country),
                'latitude': request.data.get('latitude', str(venue.latitude or '')),
                'longitude': request.data.get('longitude', str(venue.longitude or '')),
                'category': category_slug,
                'field_values': request.data.get('field_values', {}),
            }
        )

        if request.user.profile.is_trusted:
            self._apply_edit(contribution, venue)

        return Response(
            ContributionSerializer(contribution).data,
            status=status.HTTP_201_CREATED
        )

    @method_decorator(ratelimit(key='user', rate='10/d', method='POST', block=True))
    @action(detail=False, methods=['post'], url_path='venue/(?P<venue_id>[0-9]+)/add-category')
    def add_category_to_venue(self, request, venue_id=None):
        try:
            venue = Venue.objects.get(pk=venue_id, is_approved=True)
        except Venue.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)

        category_slug = request.data.get('category_slug')
        if not category_slug:
            return Response({'detail': 'category_slug required.'}, status=400)

        from apps.categories.models import Category
        try:
            category = Category.objects.get(slug=category_slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        if VenueCategory.objects.filter(venue=venue, category=category).exists():
            return Response({'detail': 'This venue is already in that category.'}, status=400)

        contribution = Contribution.objects.create(
            contributor=request.user.profile,
            contribution_type='add_category',
            venue=venue,
            payload={
                'venue_id': venue_id,
                'venue_name': venue.name,
                'category': category_slug,
                'field_values': request.data.get('field_values', {}),
            }
        )

        return Response(
            ContributionSerializer(contribution).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        try:
            contribution = Contribution.objects.get(pk=pk, status='pending')
        except Contribution.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.categories.models import Category
        try:
            category = Category.objects.get(slug=contribution.payload.get('category'))
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)

        try:
            if contribution.contribution_type == 'edit_venue':
                self._apply_edit(contribution, moderator=request.user.profile)
            elif contribution.contribution_type == 'add_category':
                self._apply_add_category(contribution, moderator=request.user.profile)
            else:
                self._apply_contribution(contribution, moderator=request.user.profile)
        except Exception as e:
            return Response({'detail': f'Error applying contribution: {str(e)}'}, status=500)

        return Response({'detail': 'Approved.'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        try:
            contribution = Contribution.objects.get(pk=pk, status='pending')
        except Contribution.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.categories.models import Category
        try:
            category = Category.objects.get(slug=contribution.payload.get('category'))
        except Category.DoesNotExist:
            return Response({'detail': 'Category not found.'}, status=404)

        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)

        contribution.status = 'rejected'
        contribution.moderator = request.user.profile
        contribution.moderation_note = request.data.get('note', '')
        contribution.moderated_at = timezone.now()
        contribution.save()

        return Response({'detail': 'Rejected.'})

    def _parse_decimal(self, value):
        try:
            v = str(value).strip()
            if not v:
                return None
            return Decimal(v).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        except Exception:
            return None

    def _extract_coords_from_url(self, map_url):
        """Extract latitude and longitude from a Google Maps URL."""
        if not map_url:
            return None, None
        
        # Pattern 1: @lat,lng,zoom
        match = re.search(r'@(-?\d+\.?\d*),(-?\d+\.?\d*)', map_url)
        if match:
            return match.group(1), match.group(2)
        
        # Pattern 2: ?q=lat,lng or query=lat,lng
        match = re.search(r'[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)', map_url)
        if match:
            return match.group(1), match.group(2)
        
        # Pattern 3: /place/lat,lng
        match = re.search(r'/place/(-?\d+\.?\d*),(-?\d+\.?\d*)', map_url)
        if match:
            return match.group(1), match.group(2)
        
        # Pattern 4: ll=lat,lng
        match = re.search(r'll=(-?\d+\.?\d*),(-?\d+\.?\d*)', map_url)
        if match:
            return match.group(1), match.group(2)
        
        return None, None

    def _apply_contribution(self, contribution, moderator=None):
        payload = contribution.payload
        from apps.categories.models import Category
        category = Category.objects.get(slug=payload['category'])

        # Try to get coordinates from payload, or extract from map_url
        lat = self._parse_decimal(payload.get('latitude'))
        lng = self._parse_decimal(payload.get('longitude'))
        
        # If no coords but we have a map_url, try to extract
        if (lat is None or lng is None) and payload.get('map_url'):
            extracted_lat, extracted_lng = self._extract_coords_from_url(payload['map_url'])
            if lat is None and extracted_lat:
                lat = self._parse_decimal(extracted_lat)
            if lng is None and extracted_lng:
                lng = self._parse_decimal(extracted_lng)

        venue = Venue.objects.create(
            name=payload['name'],
            latitude=lat,
            longitude=lng,
            city=payload.get('city', ''),
            country=payload.get('country', ''),
            is_approved=True,
        )

        venue_category = VenueCategory.objects.create(
            venue=venue,
            category=category,
            is_approved=True,
        )

        for field_name, value in payload.get('field_values', {}).items():
            try:
                field_def = FieldDefinition.objects.get(category=category, name=field_name)
                FieldValue.objects.create(venue_category=venue_category, field=field_def, value=value)
            except FieldDefinition.DoesNotExist:
                pass

        contribution.status = 'approved'
        contribution.venue = venue
        if moderator:
            contribution.moderator = moderator
        contribution.moderated_at = timezone.now()
        contribution.save()

        contributor = contribution.contributor
        contributor.contribution_count += 1
        contributor.save()

    def _apply_edit(self, contribution, venue=None, moderator=None):
        payload = contribution.payload

        if venue is None:
            venue = Venue.objects.get(pk=payload['venue_id'])

        venue.name    = payload.get('name', venue.name)
        venue.city    = payload.get('city', venue.city)
        venue.country = payload.get('country', venue.country)

        lat = self._parse_decimal(payload.get('latitude'))
        lng = self._parse_decimal(payload.get('longitude'))
        if lat is not None:
            venue.latitude = lat
        if lng is not None:
            venue.longitude = lng
        venue.save()

        from apps.categories.models import Category
        try:
            category = Category.objects.get(slug=payload.get('category'))
            venue_category, _ = VenueCategory.objects.get_or_create(
                venue=venue, category=category,
                defaults={'is_approved': True},
            )
        except Category.DoesNotExist:
            contribution.status = 'approved'
            contribution.moderated_at = timezone.now()
            contribution.save()
            return

        incoming = payload.get('field_values', {})
        for field_name, value in incoming.items():
            try:
                field_def = FieldDefinition.objects.get(category=category, name=field_name)
                FieldValue.objects.update_or_create(
                    venue_category=venue_category, field=field_def,
                    defaults={'value': value},
                )
            except FieldDefinition.DoesNotExist:
                pass

        FieldValue.objects.filter(venue_category=venue_category).exclude(
            field__name__in=incoming.keys()
        ).delete()

        contribution.status = 'approved'
        if moderator:
            contribution.moderator = moderator
        contribution.moderated_at = timezone.now()
        contribution.save()

        contributor = contribution.contributor
        contributor.contribution_count += 1
        contributor.save()

    def _apply_add_category(self, contribution, moderator=None):
        payload = contribution.payload
        venue = Venue.objects.get(pk=payload['venue_id'])

        from apps.categories.models import Category
        category = Category.objects.get(slug=payload['category'])

        venue_category, created = VenueCategory.objects.get_or_create(
            venue=venue, category=category,
            defaults={'is_approved': True},
        )
        if not created:
            venue_category.is_approved = True
            venue_category.save()

        for field_name, value in payload.get('field_values', {}).items():
            try:
                field_def = FieldDefinition.objects.get(category=category, name=field_name)
                FieldValue.objects.update_or_create(
                    venue_category=venue_category, field=field_def,
                    defaults={'value': value},
                )
            except FieldDefinition.DoesNotExist:
                pass

        contribution.status = 'approved'
        if moderator:
            contribution.moderator = moderator
        contribution.moderated_at = timezone.now()
        contribution.save()

        contributor = contribution.contributor
        contributor.contribution_count += 1
        contributor.save()


class VenueReportViewSet(viewsets.ModelViewSet):
    queryset = VenueReport.objects.all()
    serializer_class = VenueReportSerializer
    http_method_names = ['get', 'post']

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    @method_decorator(ratelimit(key='user', rate='10/d', method='POST', block=True))
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)