# apps/categories/serializers.py

from rest_framework import serializers
from .models import Category, FieldDefinition, FieldValue, FieldChoice
from django.contrib.auth.models import User


class FieldChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldChoice
        fields = ['id', 'value', 'label', 'icon', 'order', 'is_active']
        read_only_fields = ['id']


class FieldDefinitionSerializer(serializers.ModelSerializer):
    choices = serializers.SerializerMethodField()
    choices_count = serializers.SerializerMethodField()

    class Meta:
        model = FieldDefinition
        fields = [
            'id', 'name', 'label', 'field_type', 'is_required',
            'is_public', 'help_text', 'order', 'choices', 'choices_count'
        ]
        read_only_fields = ['id']

    def get_choices(self, obj):
        """Sadece choice field'lar için aktif seçenekleri döndür"""
        if obj.field_type in ('choice', 'multi_choice'):
            choices = obj.choices.filter(is_active=True).order_by('order')
            return FieldChoiceSerializer(choices, many=True).data
        return []

    def get_choices_count(self, obj):
        """Sadece choice field'lar için aktif seçenek sayısını döndür"""
        if obj.field_type in ('choice', 'multi_choice'):
            return obj.choices.filter(is_active=True).count()
        return None


class CategoryListSerializer(serializers.ModelSerializer):
    """Kategori listesi için serializer - venue_count, field_count dahil"""
    venue_count = serializers.SerializerMethodField()
    field_count = serializers.SerializerMethodField()
    owner_username = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'icon',
            'venue_count', 'field_count', 'owner_username'
        ]

    def get_venue_count(self, obj):
        """Onaylı venue sayısı"""
        return obj.venue_categories.filter(is_approved=True).count()

    def get_field_count(self, obj):
        """Field definition sayısı"""
        return obj.field_definitions.count()

    def get_owner_username(self, obj):
        """Kategori sahibinin kullanıcı adı"""
        if obj.owner:
            return obj.owner.username
        return None


class CategoryDetailSerializer(serializers.ModelSerializer):
    field_definitions = FieldDefinitionSerializer(many=True, read_only=True)
    owner = serializers.SerializerMethodField()
    moderators = serializers.SerializerMethodField()
    venue_count = serializers.SerializerMethodField()
    field_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'icon',
            'field_definitions', 'owner', 'moderators', 
            'venue_count', 'field_count'
        ]

    def get_owner(self, obj):
        if obj.owner:
            return {'id': obj.owner.id, 'username': obj.owner.username}
        return None

    def get_moderators(self, obj):
        return [{'id': m.id, 'username': m.username} for m in obj.moderators.all()]

    def get_venue_count(self, obj):
        return obj.venue_categories.filter(is_approved=True).count()

    def get_field_count(self, obj):
        return obj.field_definitions.count()


class CategoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'description', 'icon']

    def validate_slug(self, value):
        if self.instance and self.instance.slug == value:
            return value
        if Category.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Bu slug zaten kullanılıyor.")
        return value


class FieldValueSerializer(serializers.ModelSerializer):
    """FieldValue için serializer - venue form'larında kullanılır"""
    field_name = serializers.CharField(source='field.name', read_only=True)
    field_label = serializers.CharField(source='field.label', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)
    display_value = serializers.SerializerMethodField()

    class Meta:
        model = FieldValue
        fields = [
            'id', 'field', 'field_name', 'field_label', 'field_type',
            'value', 'display_value', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_display_value(self, obj):
        """Kullanıcıya gösterilecek değeri döndür"""
        return obj.get_display_value()