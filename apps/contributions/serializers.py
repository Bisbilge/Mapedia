from rest_framework import serializers
from .models import Contribution, VenueReport
from apps.categories.models import Category, FieldDefinition


class VenueContributionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    map_url = serializers.URLField(required=False, allow_blank=True)   # maps_url → map_url
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Category.objects.filter(is_active=True)
    )
    field_values = serializers.DictField(child=serializers.CharField(), required=False)

    def validate_field_values(self, value):
        category = self.initial_data.get('category')
        if not category:
            return value
        try:
            cat = Category.objects.get(slug=category)
            valid_fields = set(cat.field_definitions.values_list('name', flat=True))
            for key in value.keys():
                if key not in valid_fields:
                    raise serializers.ValidationError(f"'{key}' is not a valid field for this category.")
        except Category.DoesNotExist:
            pass
        return value

    def validate(self, attrs):
        if not attrs.get('latitude') and not attrs.get('map_url'):  # maps_url → map_url
            raise serializers.ValidationError(
                "Either latitude/longitude or map_url must be provided."
            )
        return attrs


class ContributionSerializer(serializers.ModelSerializer):
    venue_slug    = serializers.CharField(source='venue.slug', read_only=True)
    category_slug = serializers.CharField(source='venue.category.slug', read_only=True)
    name          = serializers.CharField(source='venue.name', read_only=True)
    type          = serializers.CharField(source='contribution_type', read_only=True)

    class Meta:
        model = Contribution
        fields = [
            'id', 'name', 'type', 'status', 'payload', 'created_at',
            'venue_slug', 'category_slug',
        ]
        read_only_fields = ['status', 'created_at']


class VenueReportSerializer(serializers.ModelSerializer):

    class Meta:
        model = VenueReport
        fields = ['id', 'venue', 'reason', 'description']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                validated_data['reporter'] = request.user.profile
            except:
                pass
        return super().create(validated_data)