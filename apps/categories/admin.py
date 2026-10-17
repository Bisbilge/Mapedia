# categories/admin.py

from django.contrib import admin
from .models import Category, FieldDefinition, FieldChoice, FieldValue


class FieldChoiceInline(admin.TabularInline):
    model = FieldChoice
    extra = 2
    fields = ('value', 'label', 'icon', 'order', 'is_active')
    ordering = ('order',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'owner', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('moderators',)


@admin.register(FieldDefinition)
class FieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ('label', 'category', 'field_type', 'is_required', 'order', 'choices_count')
    list_filter = ('category', 'field_type', 'is_required')
    search_fields = ('name', 'label')
    ordering = ('category', 'order')
    inlines = [FieldChoiceInline]

    def choices_count(self, obj):
        if obj.field_type in ('choice', 'multi_choice'):
            return obj.choices.filter(is_active=True).count()
        return '-'
    choices_count.short_description = 'Choices'

    def get_inline_instances(self, request, obj=None):
        """Sadece choice tipi field'lar için FieldChoice inline göster."""
        if obj and obj.field_type in ('choice', 'multi_choice'):
            return super().get_inline_instances(request, obj)
        return []


@admin.register(FieldChoice)
class FieldChoiceAdmin(admin.ModelAdmin):
    list_display = ('label', 'value', 'field', 'get_category', 'order', 'is_active')
    list_filter = ('field__category', 'field', 'is_active')
    search_fields = ('label', 'value', 'field__label')
    ordering = ('field', 'order')

    def get_category(self, obj):
        return obj.field.category.name
    get_category.short_description = 'Category'


@admin.register(FieldValue)
class FieldValueAdmin(admin.ModelAdmin):
    list_display = ('get_venue', 'get_category', 'field', 'value', 'updated_at')
    list_filter = ('field__category', 'field')
    search_fields = ('venue_category__venue__name', 'value')

    def get_venue(self, obj):
        return obj.venue_category.venue.name
    get_venue.short_description = 'Venue'

    def get_category(self, obj):
        return obj.venue_category.category.name
    get_category.short_description = 'Category'