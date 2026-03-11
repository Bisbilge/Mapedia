from rest_framework import viewsets, filters, permissions, status
from .models import Category, FieldDefinition, FieldChoice
from .serializers import (
    CategoryListSerializer, CategoryDetailSerializer,
    CategoryCreateSerializer, FieldDefinitionSerializer,
    FieldChoiceSerializer
)
from django.contrib.auth.models import User
from rest_framework.decorators import action
from rest_framework.response import Response


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CategoryDetailSerializer
        return CategoryListSerializer

    @action(detail=False, methods=['post'], url_path='create', permission_classes=[permissions.IsAuthenticated])
    def create_category(self, request):
        serializer = CategoryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        category = serializer.save(owner=request.user)
        return Response(CategoryDetailSerializer(category).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='delete', permission_classes=[permissions.IsAuthenticated])
    def delete_category(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if category.owner != request.user and not request.user.is_superuser:
            return Response({'detail': 'Forbidden.'}, status=403)
        category.delete()
        return Response({'detail': 'Deleted.'}, status=status.HTTP_204_NO_CONTENT)

    # --- MODERATOR YÖNETİMİ ---

    @action(detail=True, methods=['get'], url_path='moderators')
    def get_moderators(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if category.owner != request.user and not request.user.is_superuser:
            return Response({'detail': 'Forbidden.'}, status=403)
        mods = category.moderators.all()
        data = [{'id': m.id, 'username': m.username} for m in mods]
        return Response(data)

    @action(detail=True, methods=['post'], url_path='moderators/add')
    def add_moderator(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if category.owner != request.user and not request.user.is_superuser:
            return Response({'detail': 'Forbidden.'}, status=403)
        user_id = request.data.get('user_id')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=404)
        category.moderators.add(user)
        return Response({'detail': 'Added.', 'username': user.username})

    @action(detail=True, methods=['post'], url_path='moderators/remove')
    def remove_moderator(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if category.owner != request.user and not request.user.is_superuser:
            return Response({'detail': 'Forbidden.'}, status=403)
        user_id = request.data.get('user_id')
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=404)
        category.moderators.remove(user)
        return Response({'detail': 'Removed.'})

    # --- FIELD YÖNETİMİ ---

    @action(detail=True, methods=['get'], url_path='fields', permission_classes=[permissions.IsAuthenticated])
    def get_fields(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        fields = category.field_definitions.all().order_by('order')
        return Response(FieldDefinitionSerializer(fields, many=True).data)

    @action(detail=True, methods=['post'], url_path='fields/add', permission_classes=[permissions.IsAuthenticated])
    def add_field(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        
        # Field verilerini al
        field_data = {
            'name': request.data.get('name'),
            'label': request.data.get('label'),
            'field_type': request.data.get('field_type', 'string'),
            'is_required': request.data.get('is_required', False),
            'is_public': request.data.get('is_public', True),
            'help_text': request.data.get('help_text', ''),
            'order': request.data.get('order', 0),
        }
        
        serializer = FieldDefinitionSerializer(data=field_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        field = serializer.save(category=category)
        
        # Choice field ise choices'ları ekle
        if field.field_type in ('choice', 'multi_choice'):
            choices_data = request.data.get('choices', [])
            for choice_data in choices_data:
                if choice_data.get('value') and choice_data.get('label'):
                    FieldChoice.objects.create(
                        field=field,
                        value=choice_data['value'].strip(),
                        label=choice_data['label'].strip(),
                        icon=choice_data.get('icon', ''),
                        order=choice_data.get('order', 0),
                        is_active=True
                    )
        
        # Güncel field verisini döndür (choices dahil)
        return Response(FieldDefinitionSerializer(field).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='fields/(?P<field_id>[^/.]+)/edit', permission_classes=[permissions.IsAuthenticated])
    def edit_field(self, request, slug=None, field_id=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        try:
            field = FieldDefinition.objects.get(pk=field_id, category=category)
        except FieldDefinition.DoesNotExist:
            return Response({'detail': 'Field not found.'}, status=404)
        
        # Field güncelle (name ve field_type değiştirilemez)
        update_data = {}
        if 'label' in request.data:
            update_data['label'] = request.data['label']
        if 'is_required' in request.data:
            update_data['is_required'] = request.data['is_required']
        if 'is_public' in request.data:
            update_data['is_public'] = request.data['is_public']
        if 'help_text' in request.data:
            update_data['help_text'] = request.data['help_text']
        if 'order' in request.data:
            update_data['order'] = request.data['order']
        
        serializer = FieldDefinitionSerializer(field, data=update_data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        
        # Choices güncelle (eğer gönderildiyse)
        if 'choices' in request.data and field.field_type in ('choice', 'multi_choice'):
            choices_data = request.data.get('choices', [])
            existing_choice_ids = set(field.choices.values_list('id', flat=True))
            updated_choice_ids = set()
            
            for choice_data in choices_data:
                choice_id = choice_data.get('id')
                
                if choice_id and choice_id in existing_choice_ids:
                    # Mevcut choice'ı güncelle
                    try:
                        choice = FieldChoice.objects.get(id=choice_id, field=field)
                        choice.label = choice_data.get('label', choice.label)
                        choice.icon = choice_data.get('icon', choice.icon)
                        choice.order = choice_data.get('order', choice.order)
                        choice.is_active = choice_data.get('is_active', True)
                        choice.save()
                        updated_choice_ids.add(choice_id)
                    except FieldChoice.DoesNotExist:
                        pass
                else:
                    # Yeni choice ekle
                    if choice_data.get('value') and choice_data.get('label'):
                        new_choice = FieldChoice.objects.create(
                            field=field,
                            value=choice_data['value'].strip(),
                            label=choice_data['label'].strip(),
                            icon=choice_data.get('icon', ''),
                            order=choice_data.get('order', 0),
                            is_active=True
                        )
                        updated_choice_ids.add(new_choice.id)
            
            # Gönderilmeyen choice'ları deaktive et
            field.choices.exclude(id__in=updated_choice_ids).update(is_active=False)
        
        return Response(FieldDefinitionSerializer(field).data)

    @action(detail=True, methods=['delete'], url_path='fields/(?P<field_id>[^/.]+)/delete', permission_classes=[permissions.IsAuthenticated])
    def delete_field(self, request, slug=None, field_id=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        try:
            field = FieldDefinition.objects.get(pk=field_id, category=category)
        except FieldDefinition.DoesNotExist:
            return Response({'detail': 'Field not found.'}, status=404)
        field.delete()  # Cascade ile choices da silinir
        return Response({'detail': 'Deleted.'}, status=status.HTTP_204_NO_CONTENT)

    # --- FIELD CHOICES YÖNETİMİ ---

    @action(detail=True, methods=['get'], url_path='fields/(?P<field_id>[^/.]+)/choices', permission_classes=[permissions.IsAuthenticated])
    def get_choices(self, request, slug=None, field_id=None):
        """Bir field'ın tüm aktif choice'larını listele"""
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        try:
            field = FieldDefinition.objects.get(pk=field_id, category=category)
        except FieldDefinition.DoesNotExist:
            return Response({'detail': 'Field not found.'}, status=404)
        
        if field.field_type not in ('choice', 'multi_choice'):
            return Response({'detail': 'This field does not support choices.'}, status=400)
        
        choices = field.choices.filter(is_active=True).order_by('order')
        return Response(FieldChoiceSerializer(choices, many=True).data)

    @action(detail=True, methods=['put'], url_path='fields/(?P<field_id>[^/.]+)/choices/update', permission_classes=[permissions.IsAuthenticated])
    def update_choices(self, request, slug=None, field_id=None):
        """Bir field'ın choice'larını toplu güncelle"""
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if not category.can_moderate(request.user):
            return Response({'detail': 'Forbidden.'}, status=403)
        try:
            field = FieldDefinition.objects.get(pk=field_id, category=category)
        except FieldDefinition.DoesNotExist:
            return Response({'detail': 'Field not found.'}, status=404)
        
        if field.field_type not in ('choice', 'multi_choice'):
            return Response({'detail': 'This field does not support choices.'}, status=400)
        
        choices_data = request.data.get('choices', [])
        
        # Validasyon
        valid_choices = [c for c in choices_data if c.get('value') and c.get('label') and c.get('is_active', True)]
        if len(valid_choices) < 2:
            return Response({'detail': 'At least 2 active choices are required.'}, status=400)
        
        # Duplicate value kontrolü
        values = [c['value'].strip().lower() for c in valid_choices]
        if len(set(values)) != len(values):
            return Response({'detail': 'Choice values must be unique.'}, status=400)
        
        existing_choice_ids = set(field.choices.values_list('id', flat=True))
        updated_choice_ids = set()
        
        for idx, choice_data in enumerate(choices_data):
            choice_id = choice_data.get('id')
            is_active = choice_data.get('is_active', True)
            
            if choice_id and choice_id in existing_choice_ids:
                # Mevcut choice güncelle
                try:
                    choice = FieldChoice.objects.get(id=choice_id, field=field)
                    choice.label = choice_data.get('label', choice.label)
                    choice.icon = choice_data.get('icon', choice.icon)
                    choice.order = idx
                    choice.is_active = is_active
                    choice.save()
                    updated_choice_ids.add(choice_id)
                except FieldChoice.DoesNotExist:
                    pass
            elif choice_data.get('value') and choice_data.get('label') and is_active:
                # Yeni choice ekle
                new_choice = FieldChoice.objects.create(
                    field=field,
                    value=choice_data['value'].strip(),
                    label=choice_data['label'].strip(),
                    icon=choice_data.get('icon', ''),
                    order=idx,
                    is_active=True
                )
                updated_choice_ids.add(new_choice.id)
        
        # Güncellenmeyen mevcut choice'ları deaktive et
        field.choices.filter(id__in=existing_choice_ids - updated_choice_ids).update(is_active=False)
        
        # Güncel listeyi döndür
        choices = field.choices.filter(is_active=True).order_by('order')
        return Response(FieldChoiceSerializer(choices, many=True).data)

    @action(detail=True, methods=['patch'], url_path='update', permission_classes=[permissions.IsAuthenticated])
    def update_category(self, request, slug=None):
        try:
            category = Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=404)
        if category.owner != request.user and not request.user.is_superuser:
            return Response({'detail': 'Forbidden.'}, status=403)
        serializer = CategoryCreateSerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        serializer.save()
        return Response(CategoryDetailSerializer(serializer.instance).data)