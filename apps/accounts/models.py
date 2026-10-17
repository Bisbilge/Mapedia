# apps/users/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg
import uuid
import os


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('user', _('User')),
        ('moderator', _('Moderator')),
        ('admin', _('Admin')),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_("User")
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user',
        verbose_name=_("Role")
    )
    bio = models.TextField(blank=True, verbose_name=_("Bio"))
    avatar = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        verbose_name=_("Avatar")
    )
    contribution_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Contribution Count")
    )
    is_trusted = models.BooleanField(
        default=False,
        verbose_name=_("Trusted Contributor"),
        help_text=_("Trusted contributors' submissions are auto-approved.")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_moderator(self):
        return self.role in ('moderator', 'admin')

    @property
    def is_admin(self):
        return self.role == 'admin'

    # ============ RATING HELPER METHODS ============
    
    @property
    def ratings_given_count(self):
        """Kullanıcının verdiği toplam puan sayısı"""
        return self.user.venue_ratings.count()

    @property
    def average_rating_given(self):
        """Kullanıcının verdiği puanların ortalaması"""
        result = self.user.venue_ratings.aggregate(avg=Avg('score'))
        return round(result['avg'], 1) if result['avg'] else None

    def get_ratings_given(self):
        """Kullanıcının verdiği tüm puanlar (venue bilgisiyle)"""
        return self.user.venue_ratings.select_related('venue').order_by('-created_at')

    def get_rating_distribution(self):
        """Kullanıcının verdiği puanların dağılımı"""
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating in self.user.venue_ratings.values('score').annotate(
            count=models.Count('score')
        ):
            distribution[rating['score']] = rating['count']
        return distribution


class EmailVerificationToken(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='email_verification_token'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"VerificationToken({self.user.username})"


# ============ SIGNALS ============

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Yeni kullanıcı oluşturulduğunda otomatik profil oluştur"""
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(models.signals.post_delete, sender=UserProfile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Profil silindiğinde avatar dosyasını da sil"""
    if instance.avatar:
        if os.path.isfile(instance.avatar.path):
            os.remove(instance.avatar.path)