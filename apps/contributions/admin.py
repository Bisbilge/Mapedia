from django.contrib import admin
from .models import Contribution, VenueReport

@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ['contribution_type', 'contributor', 'venue', 'status', 'created_at']
    list_filter = ['status', 'contribution_type']
    list_editable = ['status']

@admin.register(VenueReport)
class VenueReportAdmin(admin.ModelAdmin):
    list_display = ['venue', 'reason', 'is_resolved', 'created_at']
    list_filter = ['reason', 'is_resolved']
    list_editable = ['is_resolved']