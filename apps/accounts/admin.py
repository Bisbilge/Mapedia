# apps/users/admin.py

from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django.db.models import Avg, Count
from .models import UserProfile, EmailVerificationToken


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'avatar_preview',
        'role',
        'is_trusted',
        'contribution_count',
        'ratings_stats',
        'has_bio'
    ]
    list_filter = ['role', 'is_trusted']
    list_editable = ['role', 'is_trusted']
    search_fields = ['user__username', 'user__email', 'bio']
    readonly_fields = ['created_at', 'updated_at', 'avatar_preview_large', 'ratings_detail']

    fieldsets = (
        (_('User & Permissions'), {
            'fields': ('user', 'role', 'is_trusted')
        }),
        (_('Profile Information'), {
            'fields': ('avatar', 'avatar_preview_large', 'bio')
        }),
        (_('Ratings Given'), {
            'fields': ('ratings_detail',),
            'classes': ('collapse',)
        }),
        (_('Statistics & Timestamps'), {
            'fields': ('contribution_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;" />',
                obj.avatar.url
            )
        return "-"
    avatar_preview.short_description = _('Avatar')

    def avatar_preview_large(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="max-height: 150px; border-radius: 10px;" />',
                obj.avatar.url
            )
        return "-"
    avatar_preview_large.short_description = _('Avatar Preview')

    def has_bio(self, obj):
        return bool(obj.bio)
    has_bio.boolean = True
    has_bio.short_description = _('Has Bio')

    def ratings_stats(self, obj):
        """Kullanıcının verdiği puanların özeti."""
        ratings = obj.user.venue_ratings.all()
        count = ratings.count()
        
        if count == 0:
            return mark_safe('<span style="color: #999;">—</span>')
        
        avg = ratings.aggregate(avg=Avg('score'))['avg']
        avg = round(avg, 1) if avg else 0
        
        # Renk belirleme
        if avg >= 4:
            color = "#14866d"
            bg = "#d5fdf4"
        elif avg >= 3:
            color = "#f5a623"
            bg = "#fff8e6"
        else:
            color = "#d33"
            bg = "#fee7e6"
        
        return mark_safe(
            f'<span style="background: {bg}; color: {color}; '
            f'padding: 2px 8px; font-size: 11px; border-radius: 4px;">'
            f'★ {avg} ({count})</span>'
        )
    ratings_stats.short_description = _('Ratings Given')

    def ratings_detail(self, obj):
        """Kullanıcının verdiği tüm puanların detaylı listesi."""
        ratings = obj.user.venue_ratings.select_related('venue').order_by('-created_at')[:20]
        
        if not ratings:
            return "No ratings given yet."
        
        rows = []
        for r in ratings:
            stars = '★' * r.score + '☆' * (5 - r.score)
            comment = r.comment[:40] + '...' if r.comment and len(r.comment) > 40 else (r.comment or '-')
            visible = '✓' if r.is_visible else '✗'
            
            rows.append(
                f'<tr>'
                f'<td style="padding: 4px 8px;"><a href="/admin/venues/venue/{r.venue.id}/change/">{r.venue.name}</a></td>'
                f'<td style="padding: 4px 8px; color: #f5a623;">{stars}</td>'
                f'<td style="padding: 4px 8px; color: #666; font-size: 11px;">{comment}</td>'
                f'<td style="padding: 4px 8px;">{visible}</td>'
                f'<td style="padding: 4px 8px; color: #999; font-size: 11px;">{r.created_at.strftime("%d %b %Y")}</td>'
                f'</tr>'
            )
        
        table = (
            '<table style="border-collapse: collapse; width: 100%;">'
            '<thead><tr style="background: #f5f5f5;">'
            '<th style="padding: 6px 8px; text-align: left;">Venue</th>'
            '<th style="padding: 6px 8px; text-align: left;">Score</th>'
            '<th style="padding: 6px 8px; text-align: left;">Comment</th>'
            '<th style="padding: 6px 8px; text-align: left;">Visible</th>'
            '<th style="padding: 6px 8px; text-align: left;">Date</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            '</table>'
        )
        
        total = obj.user.venue_ratings.count()
        if total > 20:
            table += f'<p style="color: #666; font-size: 12px; margin-top: 8px;">Showing 20 of {total} ratings.</p>'
        
        return mark_safe(table)
    ratings_detail.short_description = _('Recent Ratings')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('user__venue_ratings')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token', 'created_at']
    search_fields = ['user__username', 'user__email', 'token']
    readonly_fields = ['created_at']