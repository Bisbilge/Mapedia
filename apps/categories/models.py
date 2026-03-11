# categories/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User


class Category(models.Model):
    name        = models.CharField(max_length=255, verbose_name=_("Category Name"))
    slug        = models.SlugField(max_length=255, unique=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    icon        = models.CharField(max_length=100, blank=True, verbose_name=_("Icon"))
    is_active   = models.BooleanField(default=True, verbose_name=_("Active"))
    owner       = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_categories', verbose_name=_("Owner")
    )
    moderators = models.ManyToManyField(
        User, blank=True, related_name='moderated_categories', verbose_name=_("Moderators")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("Category")
        verbose_name_plural = _("Categories")
        ordering            = ['name']

    def __str__(self):
        return self.name

    def can_moderate(self, user):
        if user.is_superuser:
            return True
        if self.owner == user:
            return True
        if self.moderators.filter(pk=user.pk).exists():
            return True
        return False


class FieldDefinition(models.Model):
    FIELD_TYPES = [
        ('boolean', _('Boolean (Yes/No)')),
        ('string',  _('Short Text')),
        ('text',    _('Long Text')),
        ('integer', _('Integer')),
        ('decimal', _('Decimal')),
        ('url',     _('URL')),
        ('choice',  _('Single Choice')),
        ('multi_choice', _('Multiple Choice')),
    ]

    category    = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name='field_definitions', verbose_name=_("Category")
    )
    name        = models.CharField(max_length=100, verbose_name=_("Field Name"))
    label       = models.CharField(max_length=255, verbose_name=_("Display Label"))
    field_type  = models.CharField(max_length=20, choices=FIELD_TYPES, verbose_name=_("Field Type"))
    is_required = models.BooleanField(default=False, verbose_name=_("Required"))
    is_public   = models.BooleanField(default=True,  verbose_name=_("Public"))
    help_text   = models.CharField(max_length=500, blank=True, verbose_name=_("Help Text"))
    order       = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("Field Definition")
        verbose_name_plural = _("Field Definitions")
        ordering            = ['order']
        unique_together     = ['category', 'name']

    def __str__(self):
        return f"{self.category.name} - {self.label}"

    @property
    def is_choice_field(self):
        """Bu field bir seçenek tipi mi?"""
        return self.field_type in ('choice', 'multi_choice')


class FieldChoice(models.Model):
    """
    FieldDefinition için tanımlanabilir seçenekler.
    Sadece field_type='choice' veya 'multi_choice' olan field'lar için kullanılır.
    """
    field = models.ForeignKey(
        FieldDefinition, 
        on_delete=models.CASCADE,
        related_name='choices', 
        verbose_name=_("Field")
    )
    value = models.CharField(
        max_length=100, 
        verbose_name=_("Value"),
        help_text=_("Internal value stored in database")
    )
    label = models.CharField(
        max_length=255, 
        verbose_name=_("Display Label"),
        help_text=_("Label shown to users")
    )
    icon = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name=_("Icon"),
        help_text=_("Optional icon class (e.g., 'fa-credit-card')")
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("Field Choice")
        verbose_name_plural = _("Field Choices")
        ordering            = ['order', 'label']
        unique_together     = ['field', 'value']

    def __str__(self):
        return f"{self.field.label} → {self.label}"


class FieldValue(models.Model):
    """
    Field values are now tied to a VenueCategory membership,
    not directly to a Venue. This allows each category to have
    its own set of field values for the same venue.
    
    For choice/multi_choice fields:
    - choice: value contains a single FieldChoice.value
    - multi_choice: value contains JSON array of FieldChoice.value's
    """
    venue_category = models.ForeignKey(
        'venues.VenueCategory', on_delete=models.CASCADE,
        related_name='field_values', verbose_name=_("Venue Category")
    )
    field = models.ForeignKey(
        FieldDefinition, on_delete=models.CASCADE,
        related_name='values', verbose_name=_("Field")
    )
    value      = models.TextField(verbose_name=_("Value"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("Field Value")
        verbose_name_plural = _("Field Values")
        unique_together     = ['venue_category', 'field']

    def __str__(self):
        return f"{self.venue_category.venue.name} | {self.venue_category.category.name} | {self.field.label}: {self.value}"

    def get_display_value(self):
        """Değeri kullanıcıya gösterilecek formatta döndür."""
        if self.field.field_type == 'boolean':
            return _("Yes") if self.value.lower() in ('true', '1', 'yes') else _("No")
        
        elif self.field.field_type == 'choice':
            # Tek seçim - label'ı bul
            try:
                choice = self.field.choices.get(value=self.value, is_active=True)
                return choice.label
            except FieldChoice.DoesNotExist:
                return self.value
        
        elif self.field.field_type == 'multi_choice':
            # Çoklu seçim - JSON array
            import json
            try:
                values = json.loads(self.value)
            except (json.JSONDecodeError, TypeError):
                values = [v.strip() for v in self.value.split(',') if v.strip()]
            
            labels = []
            for val in values:
                try:
                    choice = self.field.choices.get(value=val, is_active=True)
                    labels.append(choice.label)
                except FieldChoice.DoesNotExist:
                    labels.append(val)
            return ', '.join(labels)
        
        return self.value

    def get_selected_choices(self):
        """Seçili FieldChoice nesnelerini döndür (choice/multi_choice için)."""
        if not self.field.is_choice_field:
            return FieldChoice.objects.none()
        
        import json
        if self.field.field_type == 'choice':
            return self.field.choices.filter(value=self.value, is_active=True)
        
        # multi_choice
        try:
            values = json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            values = [v.strip() for v in self.value.split(',') if v.strip()]
        
        return self.field.choices.filter(value__in=values, is_active=True)