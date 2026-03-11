# apps/venues/serializers.py

from rest_framework import serializers
from .models import Venue, VenueCategory, VenueRating
from apps.categories.models import FieldValue, FieldChoice
from django.db.models import Avg
import json


class FieldChoiceSerializer(serializers.ModelSerializer):
    """Choice seçenekleri için serializer"""
    class Meta:
        model = FieldChoice
        fields = ['id', 'value', 'label', 'icon', 'order']


class FieldValueSerializer(serializers.ModelSerializer):
    field_name = serializers.CharField(source='field.name', read_only=True)
    field_label = serializers.CharField(source='field.label', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)
    
    display_value = serializers.SerializerMethodField()
    selected_choices = serializers.SerializerMethodField()

    class Meta:
        model = FieldValue
        fields = [
            'id', 'field', 'field_name', 'field_label', 'field_type',
            'value', 'display_value', 'selected_choices'
        ]

    def get_display_value(self, obj):
        """Kullanıcıya gösterilecek değer (label'lar)"""
        if obj.field.field_type == 'boolean':
            if obj.value.lower() in ('true', '1', 'yes'):
                return 'Yes'
            elif obj.value.lower() in ('false', '0', 'no'):
                return 'No'
            return 'Unknown'

        elif obj.field.field_type == 'choice':
            try:
                choice = obj.field.choices.get(value=obj.value, is_active=True)
                return choice.label
            except FieldChoice.DoesNotExist:
                return obj.value

        elif obj.field.field_type == 'multi_choice':
            try:
                values = json.loads(obj.value)
            except (json.JSONDecodeError, TypeError):
                values = [v.strip() for v in obj.value.split(',') if v.strip()]

            labels = []
            for val in values:
                try:
                    choice = obj.field.choices.get(value=val, is_active=True)
                    labels.append(choice.label)
                except FieldChoice.DoesNotExist:
                    labels.append(val)
            return ', '.join(labels)

        return obj.value

    def get_selected_choices(self, obj):
        """Choice/multi_choice için seçili choice nesneleri"""
        if obj.field.field_type not in ('choice', 'multi_choice'):
            return None

        if obj.field.field_type == 'choice':
            try:
                choice = obj.field.choices.get(value=obj.value, is_active=True)
                return [FieldChoiceSerializer(choice).data]
            except FieldChoice.DoesNotExist:
                return []

        elif obj.field.field_type == 'multi_choice':
            try:
                values = json.loads(obj.value)
            except (json.JSONDecodeError, TypeError):
                values = [v.strip() for v in obj.value.split(',') if v.strip()]

            choices = obj.field.choices.filter(value__in=values, is_active=True)
            return FieldChoiceSerializer(choices, many=True).data

        return None


class VenueCategorySerializer(serializers.ModelSerializer):
    """One category membership with its field values."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    field_values = FieldValueSerializer(many=True, read_only=True)

    class Meta:
        model = VenueCategory
        fields = ['id', 'category', 'category_name', 'category_slug', 'is_approved', 'field_values']


# ============ RATING SERIALIZERS ============

class VenueRatingUserSerializer(serializers.Serializer):
    """Rating içindeki kullanıcı bilgisi"""
    id = serializers.IntegerField()
    username = serializers.CharField()
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'profile') and obj.profile.avatar:
            if request:
                return request.build_absolute_uri(obj.profile.avatar.url)
            return obj.profile.avatar.url
        return None


class VenueRatingSerializer(serializers.ModelSerializer):
    """Rating okuma için serializer"""
    user = serializers.SerializerMethodField()

    class Meta:
        model = VenueRating
        fields = [
            'id', 'score', 'comment', 
            'user', 'created_at', 'updated_at'
        ]

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'avatar': self._get_avatar_url(obj.user)
        }

    def _get_avatar_url(self, user):
        request = self.context.get('request')
        if hasattr(user, 'profile') and user.profile.avatar:
            if request:
                return request.build_absolute_uri(user.profile.avatar.url)
            return user.profile.avatar.url
        return None


class VenueRatingCreateSerializer(serializers.ModelSerializer):
    """Rating oluşturma/güncelleme için serializer"""
    
    class Meta:
        model = VenueRating
        fields = ['score', 'comment']

    def validate_score(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Score must be between 1 and 5.")
        return value

    def validate_comment(self, value):
        if value and len(value) > 500:
            raise serializers.ValidationError("Comment cannot exceed 500 characters.")
        return value


class VenueRatingDetailSerializer(serializers.ModelSerializer):
    """Rating detay (venue bilgisiyle birlikte)"""
    user = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()

    class Meta:
        model = VenueRating
        fields = [
            'id', 'score', 'comment',
            'user', 'venue',
            'created_at', 'updated_at'
        ]

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
        }

    def get_venue(self, obj):
        return {
            'id': obj.venue.id,
            'name': obj.venue.name,
            'slug': obj.venue.slug,
            'city': obj.venue.city,
            'country': obj.venue.country,
        }


# ============ VENUE SERIALIZERS ============

class VenueMapSerializer(serializers.ModelSerializer):
    """Harita için minimal venue bilgisi"""
    average_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = ['id', 'name', 'slug', 'latitude', 'longitude', 'average_rating', 'rating_count']

    def get_average_rating(self, obj):
        return obj.average_rating

    def get_rating_count(self, obj):
        return obj.rating_count


class VenueListSerializer(serializers.ModelSerializer):
    """Venue listesi için serializer"""
    categories = VenueCategorySerializer(source='venue_categories', many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = [
            'id', 'name', 'slug', 'latitude', 'longitude', 
            'city', 'country', 'is_approved', 
            'categories',
            'average_rating', 'rating_count'
        ]

    def get_average_rating(self, obj):
        return obj.average_rating

    def get_rating_count(self, obj):
        return obj.rating_count


# ─────────────────────────────────────────────
# SEO: Nearby / Related venue'lar için minimal serializer.
# VenueDetailSerializer içinde kullanılır.
# primary_category_slug: RelatedVenues bileşenindeki
# "Browse all X venues →" linkini oluşturmak için gerekli.
# ─────────────────────────────────────────────
class VenueNearbySerializer(serializers.ModelSerializer):
    """nearby_venues ve related_venues için minimal serializer."""
    primary_category_slug = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = ['slug', 'name', 'city', 'average_rating', 'primary_category_slug']

    def get_primary_category_slug(self, obj):
        # venue_categories__category prefetch varsa DB'ye gitme
        vc = obj.venue_categories.filter(is_approved=True).select_related('category').first()
        return vc.category.slug if vc else None


class VenueDetailSerializer(serializers.ModelSerializer):
    """Venue detay sayfası için serializer"""
    categories = VenueCategorySerializer(source='venue_categories', many=True, read_only=True)
    schema_data = serializers.SerializerMethodField()
    contributors = serializers.SerializerMethodField()
    
    # Rating bilgileri
    average_rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    rating_breakdown = serializers.SerializerMethodField()
    recent_ratings = serializers.SerializerMethodField()

    # ── SEO: İç linkleme alanları ──────────────────────────────────────
    # nearby_venues:  aynı şehir + aynı birincil kategori → coğrafi küme
    # related_venues: aynı kategori + farklı şehir       → tematik küme
    # Her ikisi de max 6 kayıt, rating'e göre sıralı.
    # Frontend'de NearbyVenues ve RelatedVenues bileşenleri render eder.
    nearby_venues = serializers.SerializerMethodField()
    related_venues = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = [
            'id', 'name', 'slug', 'latitude', 'longitude',
            'city', 'country',
            'is_approved', 'is_active',
            'categories',
            'contributors',
            'average_rating', 'rating_count', 'rating_breakdown', 'recent_ratings',
            'nearby_venues', 'related_venues',
            'created_at', 'updated_at',
            'schema_data',
        ]

    def get_average_rating(self, obj):
        return obj.average_rating

    def get_rating_count(self, obj):
        return obj.rating_count

    def get_rating_breakdown(self, obj):
        """Her yıldız için kaç oy var"""
        return obj.get_rating_breakdown()

    def get_recent_ratings(self, obj):
        """Son 5 rating"""
        ratings = obj.ratings.filter(is_visible=True).select_related('user__profile').order_by('-created_at')[:5]
        return VenueRatingSerializer(ratings, many=True, context=self.context).data

    def _get_primary_category(self, obj):
        """İlk onaylı kategoriyi döner (nearby/related hesaplamada ortak kullanım)."""
        return (
            obj.venue_categories
            .filter(is_approved=True)
            .select_related('category')
            .first()
        )

    def get_nearby_venues(self, obj):
        """
        Aynı şehir + aynı birincil kategori, max 6 mekan.
        Şehir yoksa boş liste döner.
        distinct() + annotate ORDER BY çakışmasını önlemek için
        subquery pattern: önce id'leri al, sonra sırala.
        """
        if not obj.city:
            return []

        primary_vc = self._get_primary_category(obj)

        qs = (
            Venue.objects
            .filter(city__iexact=obj.city, is_approved=True, is_active=True)
            .exclude(pk=obj.pk)
        )

        if primary_vc:
            qs = qs.filter(
                venue_categories__category=primary_vc.category,
                venue_categories__is_approved=True,
            )

        # distinct() + annotate ORDER BY çakışmasını önle:
        # 1. id listesini distinct ile al
        # 2. annotate + order_by'ı temiz queryset'te uygula
        venue_ids = qs.values_list('id', flat=True).distinct()
        qs = (
            Venue.objects
            .filter(id__in=venue_ids)
            .annotate(avg_score=Avg('ratings__score'))
            .prefetch_related('venue_categories__category')
            .order_by('-avg_score', '-created_at')[:6]
        )

        return VenueNearbySerializer(qs, many=True).data

    def get_related_venues(self, obj):
        """
        Aynı birincil kategori + farklı şehir, max 6 mekan.
        Şehri olmayan venue'ları da dahil eder.
        """
        primary_vc = self._get_primary_category(obj)
        if not primary_vc:
            return []

        qs = (
            Venue.objects
            .filter(
                venue_categories__category=primary_vc.category,
                venue_categories__is_approved=True,
                is_approved=True,
                is_active=True,
            )
            .exclude(pk=obj.pk)
        )

        if obj.city:
            qs = qs.exclude(city__iexact=obj.city)

        # Aynı pattern: id subquery → temiz annotate
        venue_ids = qs.values_list('id', flat=True).distinct()
        qs = (
            Venue.objects
            .filter(id__in=venue_ids)
            .annotate(avg_score=Avg('ratings__score'))
            .prefetch_related('venue_categories__category')
            .order_by('-avg_score', '-created_at')[:6]
        )

        return VenueNearbySerializer(qs, many=True).data

    def get_schema_data(self, obj):
        """Google Rich Results için JSON-LD"""
        schema = {
            "@context": "https://schema.org",
            "@type": "Place",
            "name": obj.name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": obj.city,
                "addressCountry": obj.country
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": str(obj.latitude),
                "longitude": str(obj.longitude)
            },
            "url": f"https://mapedia.org/venue/{obj.slug}",
        }
        
        # Rating varsa schema'ya ekle
        if obj.rating_count > 0:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": str(obj.average_rating),
                "ratingCount": obj.rating_count,
                "bestRating": "5",
                "worstRating": "1"
            }
        
        return schema

    def get_contributors(self, obj):
        unique_users = set()
        contributors_data = []

        # 1. VenueContributor tablosundan
        if hasattr(obj, 'contributors'):
            for contrib in obj.contributors.select_related('user'):
                if contrib.user:
                    username = contrib.user.username
                    if username not in unique_users:
                        unique_users.add(username)
                        contributors_data.append({'username': username})

        # 2. Contribution tablosundan
        from apps.contributions.models import Contribution
        approved_contributions = Contribution.objects.filter(
            venue=obj,
            status='approved'
        ).select_related('contributor__user')

        for c in approved_contributions:
            if c.contributor and c.contributor.user:
                username = c.contributor.user.username
                if username not in unique_users:
                    unique_users.add(username)
                    contributors_data.append({'username': username})

        return contributors_data