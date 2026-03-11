from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap, index as sitemap_index
from apps.venues.sitemaps import VenueSitemap
from apps.categories.sitemaps import CategorySitemap

sitemaps = {
    'venues': VenueSitemap,
    'categories': CategorySitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap_index, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.index'),
    path('sitemap-<section>.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('api/v1/', include('apps.venues.urls')),
    path('api/v1/', include('apps.categories.urls')),
    path('api/v1/', include('apps.contributions.urls')),
    path('api/v1/', include('apps.accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)