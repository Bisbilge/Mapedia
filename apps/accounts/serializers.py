# apps/users/serializers.py

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db.models import Avg
from rest_framework import serializers
from .models import UserProfile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    accept_terms = serializers.BooleanField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'accept_terms']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'This email is already in use.'})
        if not attrs.get('accept_terms'):
            raise serializers.ValidationError({
                'accept_terms': 'You must accept the Terms of Service and Privacy Policy to register.'
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        validated_data.pop('accept_terms')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            is_active=False,
        )
        UserProfile.objects.get_or_create(user=user)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    
    # Rating istatistikleri
    ratings_given_count = serializers.SerializerMethodField()
    average_rating_given = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'username',
            'email',
            'role',
            'bio',
            'avatar',
            'contribution_count',
            'is_trusted',
            'ratings_given_count',
            'average_rating_given',
        ]
        read_only_fields = ['role', 'contribution_count', 'is_trusted']

    def get_ratings_given_count(self, obj):
        return obj.user.venue_ratings.count()

    def get_average_rating_given(self, obj):
        result = obj.user.venue_ratings.aggregate(avg=Avg('score'))
        return round(result['avg'], 1) if result['avg'] else None


class UserProfilePublicSerializer(serializers.ModelSerializer):
    """Public profil için serializer (email yok)"""
    id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    avatar = serializers.SerializerMethodField()
    
    # Rating istatistikleri
    ratings_given_count = serializers.SerializerMethodField()
    average_rating_given = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'username',
            'date_joined',
            'role',
            'bio',
            'avatar',
            'contribution_count',
            'is_trusted',
            'ratings_given_count',
            'average_rating_given',
        ]

    def get_avatar(self, obj):
        request = self.context.get('request')
        if obj.avatar:
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def get_ratings_given_count(self, obj):
        return obj.user.venue_ratings.filter(is_visible=True).count()

    def get_average_rating_given(self, obj):
        result = obj.user.venue_ratings.filter(is_visible=True).aggregate(avg=Avg('score'))
        return round(result['avg'], 1) if result['avg'] else None


class UserRatingSerializer(serializers.Serializer):
    """Kullanıcının verdiği rating listesi için"""
    id = serializers.IntegerField()
    score = serializers.IntegerField()
    comment = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    venue = serializers.SerializerMethodField()

    def get_venue(self, obj):
        return {
            'id': obj.venue.id,
            'name': obj.venue.name,
            'slug': obj.venue.slug,
            'city': obj.venue.city,
            'country': obj.venue.country,
        }


class UserSearchSerializer(serializers.Serializer):
    """Kullanıcı arama sonuçları için"""
    id = serializers.IntegerField()
    username = serializers.CharField()
    avatar = serializers.SerializerMethodField()
    contribution_count = serializers.IntegerField()
    ratings_count = serializers.IntegerField()
    is_trusted = serializers.BooleanField()
    date_joined = serializers.DateTimeField()

    def get_avatar(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'profile') and obj.profile.avatar:
            if request:
                return request.build_absolute_uri(obj.profile.avatar.url)
            return obj.profile.avatar.url
        return None


class LeaderboardUserSerializer(serializers.Serializer):
    """Leaderboard için kullanıcı serializer"""
    id = serializers.IntegerField()
    username = serializers.CharField()
    avatar = serializers.SerializerMethodField()
    contribution_count = serializers.IntegerField()
    ratings_count = serializers.IntegerField()
    average_rating_given = serializers.FloatField(allow_null=True)
    is_trusted = serializers.BooleanField()
    date_joined = serializers.DateTimeField()

    def get_avatar(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'profile') and obj.profile.avatar:
            if request:
                return request.build_absolute_uri(obj.profile.avatar.url)
            return obj.profile.avatar.url
        return None