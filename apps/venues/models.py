# apps/venues/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.db.models import Avg
from simple_history.models import HistoricalRecords


class Venue(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Venue Name"))
    slug = models.SlugField(max_length=255, unique=True, blank=True, verbose_name=_("Slug"))
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True, verbose_name=_("Latitude")
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True, verbose_name=_("Longitude")
    )
    city = models.CharField(max_length=100, blank=True, verbose_name=_("City"))
    country = models.CharField(max_length=100, blank=True, verbose_name=_("Country"))
    
    is_approved = models.BooleanField(default=False, verbose_name=_("Approved"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Venue")
        verbose_name_plural = _("Venues")
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Venue.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # ============ RATING HELPER METHODS ============
    
    @property
    def average_rating(self):
        """Ortalama puan (1-5 arası, virgülden sonra 1 basamak)"""
        result = self.ratings.aggregate(avg=Avg('score'))
        return round(result['avg'], 1) if result['avg'] else None

    @property
    def rating_count(self):
        """Toplam oy sayısı"""
        return self.ratings.count()

    def get_rating_breakdown(self):
        """Her yıldız için kaç oy var"""
        breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating in self.ratings.values('score').annotate(count=models.Count('score')):
            breakdown[rating['score']] = rating['count']
        return breakdown

    def get_user_rating(self, user):
        """Belirli bir kullanıcının bu mekana verdiği puan"""
        if not user or not user.is_authenticated:
            return None
        try:
            return self.ratings.get(user=user).score
        except VenueRating.DoesNotExist:
            return None


class VenueContributor(models.Model):
    """Mekana katkıda bulunan kullanıcılar"""
    
    CONTRIBUTION_TYPES = [
        ('added', _('Added the place')),
        ('updated', _('Updated information')),
        ('imported', _('Imported from Open Data')),
    ]

    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name='contributors'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='venue_contributions'
    )
    contribution_type = models.CharField(
        max_length=20,
        choices=CONTRIBUTION_TYPES,
        default='updated'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Contributor")
        verbose_name_plural = _("Contributors")
        unique_together = ['venue', 'user', 'contribution_type']

    def __str__(self):
        return f"{self.user.username} - {self.venue.name} ({self.get_contribution_type_display()})"


class VenueCategory(models.Model):
    """Mekanın ait olduğu kategoriler"""
    
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name='venue_categories'
    )
    category = models.ForeignKey(
        'categories.Category',
        on_delete=models.CASCADE,
        related_name='venue_categories'
    )
    is_approved = models.BooleanField(default=False, verbose_name=_("Approved"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Venue Category")
        verbose_name_plural = _("Venue Categories")
        unique_together = ['venue', 'category']

    def __str__(self):
        return f"{self.venue.name} — {self.category.name}"


class VenueRating(models.Model):
    """Kullanıcıların mekanlara verdiği yıldız puanları"""
    
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name='ratings',
        verbose_name=_("Venue")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='venue_ratings',
        verbose_name=_("User")
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name=_("Score"),
        help_text=_("1-5 arası puan")
    )
    comment = models.TextField(
        blank=True,
        verbose_name=_("Comment"),
        help_text=_("Opsiyonel kısa yorum (max 500 karakter)")
    )
    
    # Moderasyon için
    is_visible = models.BooleanField(
        default=True,
        verbose_name=_("Visible"),
        help_text=_("Spam/uygunsuz yorumlar gizlenebilir")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Venue Rating")
        verbose_name_plural = _("Venue Ratings")
        unique_together = ['venue', 'user']  # Bir kullanıcı bir mekana 1 kez puan verir
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} → {self.venue.name}: {self.score}★"