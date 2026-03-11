# apps/venues/admin.py

from django.contrib import admin
from django.utils.html import mark_safe
from django.db.models import Avg, Count
from .models import Venue, VenueCategory, VenueContributor, VenueRating
from apps.contributions.models import Contribution


class VenueContributorInline(admin.TabularInline):
    """Mekanın detayında bot veya manuel atanan katkıcıları yönetir."""
    model = VenueContributor
    extra = 0
    autocomplete_fields = ['user']
    verbose_name = "Contributor (Imported/Manual)"
    verbose_name_plural = "Contributors (Imported/Manual)"


class ApprovedContributionInline(admin.TabularInline):
    """Mekanın detayında kullanıcıların onaylanmış düzenleme başvurularını gösterir."""
    model = Contribution
    extra = 0
    fields = ['contributor', 'contribution_type', 'status', 'created_at']
    readonly_fields = ['contributor', 'contribution_type', 'status', 'created_at']
    can_delete = False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status='approved').select_related('contributor__user')


class VenueCategoryInline(admin.TabularInline):
    """Mekanın dahil olduğu kategorileri yönetir."""
    model = VenueCategory
    extra = 1
    autocomplete_fields = ['category']
    fields = ['category', 'is_approved', 'created_at']
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')


class VenueRatingInline(admin.TabularInline):
    """Mekanın aldığı puanları gösterir."""
    model = VenueRating
    extra = 0
    fields = ['user', 'score', 'comment_preview', 'is_visible', 'created_at']
    readonly_fields = ['user', 'score', 'comment_preview', 'created_at']
    can_delete = True

    def comment_preview(self, obj):
        if obj.comment:
            preview = obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
            return preview
        return '-'
    comment_preview.short_description = 'Comment'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'city',
        'get_categories',
        'get_rating_display',
        'get_contributors',
        'is_approved',
        'is_active',
        'created_at'
    ]
    list_filter = ['is_approved', 'is_active', 'country', 'venue_categories__category']
    search_fields = ['name', 'city', 'slug']
    list_editable = ['is_approved', 'is_active']
    prepopulated_fields = {'slug': ('name',)}

    inlines = [VenueCategoryInline, VenueRatingInline, VenueContributorInline, ApprovedContributionInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'is_approved', 'is_active')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude', 'city', 'country')
        }),
    )

    def get_categories(self, obj):
        """Kategorileri renkli rozetler olarak gösterir."""
        categories = obj.venue_categories.all()
        if not categories:
            return mark_safe('<span style="color: #999;">—</span>')

        links = []
        for vc in categories:
            color_bg = "#d5fdf4" if vc.is_approved else "#fee7e6"
            color_txt = "#14866d" if vc.is_approved else "#d33"
            symbol = "✓" if vc.is_approved else "○"
            links.append(
                f'<span style="background: {color_bg}; color: {color_txt}; '
                f'padding: 2px 8px; margin-right: 4px; font-size: 11px; border-radius: 4px;">'
                f'{symbol} {vc.category.name}</span>'
            )
        return mark_safe(' '.join(links))
    get_categories.short_description = 'Categories'

    def get_rating_display(self, obj):
        """Rating'i yıldızlı badge olarak gösterir."""
        if hasattr(obj, 'avg_rating') and obj.avg_rating:
            avg = round(obj.avg_rating, 1)
            count = obj.rating_count_annotated or 0
            
            # Yıldız rengi
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
                f'padding: 3px 8px; font-size: 12px; border-radius: 4px; font-weight: 600;">'
                f'★ {avg} <small style="font-weight: normal;">({count})</small></span>'
            )
        return mark_safe('<span style="color: #999;">—</span>')
    get_rating_display.short_description = 'Rating'
    get_rating_display.admin_order_field = 'avg_rating'

    def get_contributors(self, obj):
        """Hem botları hem de onaylı kullanıcıları tek sütunda listeler."""
        v_users = [vc.user.username for vc in obj.contributors.all() if vc.user]
        c_users = [c.contributor.user.username for c in obj.contributions.all()
                   if c.status == 'approved' and c.contributor and c.contributor.user]

        all_users = list(set(v_users + c_users))

        if not all_users:
            return mark_safe('<span style="color: #999;">No contributors</span>')

        badges = []
        for user in all_users:
            bg = "#e0e0e0" if "bot" in user.lower() or "user" in user.lower() else "#e3f2fd"
            badges.append(
                f'<span style="background: {bg}; padding: 2px 5px; border-radius: 3px; '
                f'font-size: 10px; margin-right: 3px;">@{user}</span>'
            )
        return mark_safe(' '.join(badges))
    get_contributors.short_description = 'Contributors'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'venue_categories__category',
            'contributors__user',
            'contributions__contributor__user',
            'ratings'
        ).annotate(
            avg_rating=Avg('ratings__score'),
            rating_count_annotated=Count('ratings')
        )


@admin.register(VenueCategory)
class VenueCategoryAdmin(admin.ModelAdmin):
    list_display = ['venue', 'category', 'is_approved', 'field_values_count', 'created_at']
    list_filter = ['is_approved', 'category']
    list_editable = ['is_approved']
    search_fields = ['venue__name', 'category__name']
    autocomplete_fields = ['venue', 'category']

    def field_values_count(self, obj):
        count = obj.field_values.count()
        color = "#14866d" if count > 0 else "#999"
        return mark_safe(f'<span style="color: {color};">{count}</span>')
    field_values_count.short_description = 'Fields'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('venue', 'category').prefetch_related('field_values')


@admin.register(VenueContributor)
class VenueContributorAdmin(admin.ModelAdmin):
    list_display = ['venue', 'user', 'contribution_type', 'created_at']
    search_fields = ['venue__name', 'user__username']
    list_filter = ['contribution_type']
    autocomplete_fields = ['venue', 'user']


@admin.register(VenueRating)
class VenueRatingAdmin(admin.ModelAdmin):
    list_display = [
        'venue',
        'user',
        'score_display',
        'comment_preview',
        'is_visible',
        'created_at'
    ]
    list_filter = ['score', 'is_visible', 'created_at']
    list_editable = ['is_visible']
    search_fields = ['venue__name', 'user__username', 'comment']
    autocomplete_fields = ['venue', 'user']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('venue', 'user', 'score')
        }),
        ('Comment', {
            'fields': ('comment',)
        }),
        ('Moderation', {
            'fields': ('is_visible',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def score_display(self, obj):
        """Puanı yıldızlı olarak gösterir."""
        stars = '★' * obj.score + '☆' * (5 - obj.score)
        
        if obj.score >= 4:
            color = "#14866d"
        elif obj.score >= 3:
            color = "#f5a623"
        else:
            color = "#d33"
        
        return mark_safe(f'<span style="color: {color}; font-size: 14px;">{stars}</span>')
    score_display.short_description = 'Score'
    score_display.admin_order_field = 'score'

    def comment_preview(self, obj):
        """Yorumun kısa önizlemesi."""
        if obj.comment:
            preview = obj.comment[:80] + '...' if len(obj.comment) > 80 else obj.comment
            return preview
        return mark_safe('<span style="color: #999;">—</span>')
    comment_preview.short_description = 'Comment'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('venue', 'user')

    actions = ['make_visible', 'make_hidden']

    @admin.action(description='Mark selected ratings as visible')
    def make_visible(self, request, queryset):
        updated = queryset.update(is_visible=True)
        self.message_user(request, f'{updated} rating(s) marked as visible.')

    @admin.action(description='Mark selected ratings as hidden')
    def make_hidden(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, f'{updated} rating(s) marked as hidden.')