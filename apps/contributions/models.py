from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Contribution(models.Model):

    STATUS_CHOICES = [
        ('pending', _('Pending Review')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
    ]

    CONTRIBUTION_TYPES = [
        ('add_venue', _('Add New Venue')),
        ('edit_venue', _('Edit Venue')),
        ('add_field_value', _('Add Field Value')),
        ('edit_field_value', _('Edit Field Value')),
        ('add_category', _('Add Category to Venue')),
    ]

    contributor = models.ForeignKey(
        'accounts.UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contributions',
        verbose_name=_("Contributor")
    )
    venue = models.ForeignKey(
        'venues.Venue',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='contributions',
        verbose_name=_("Venue")
    )
    contribution_type = models.CharField(
        max_length=20,
        choices=CONTRIBUTION_TYPES,
        verbose_name=_("Contribution Type")
    )
    payload = models.JSONField(verbose_name=_("Payload"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_("Status")
    )
    moderator = models.ForeignKey(
        'accounts.UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_contributions',
        verbose_name=_("Moderator")
    )
    moderation_note = models.TextField(blank=True, verbose_name=_("Moderation Note"))
    moderated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Moderated At"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Contribution")
        verbose_name_plural = _("Contributions")
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_status_display()}] {self.get_contribution_type_display()}"


class VenueReport(models.Model):

    REASON_CHOICES = [
        ('closed', _('Venue Closed / Not Found')),
        ('wrong_location', _('Wrong Location on Map')),
        ('wrong_info', _('Incorrect Information')),
        ('inappropriate', _('Inappropriate Content')),
        ('duplicate', _('Duplicate Entry')),
        ('other', _('Other')),
    ]

    venue = models.ForeignKey(
        'venues.Venue',
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name=_("Venue")
    )
    reporter = models.ForeignKey(
        'accounts.UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
        verbose_name=_("Reporter")
    )
    reason = models.CharField(max_length=50, choices=REASON_CHOICES, verbose_name=_("Reason"))
    description = models.TextField(blank=True, verbose_name=_("Additional Details"))
    is_resolved = models.BooleanField(default=False, verbose_name=_("Resolved"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Venue Report")
        verbose_name_plural = _("Venue Reports")
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_reason_display()}] {self.venue.name}"