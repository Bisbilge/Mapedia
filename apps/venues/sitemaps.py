from django.contrib.sitemaps import Sitemap
from .models import Venue

class VenueSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        # Sadece onaylanmış ve aktif mekanları sitemap'e eklemek SEO açısından daha sağlıklıdır
        return Venue.objects.filter(is_active=True, is_approved=True)

    def location(self, obj):
        return f'/venue/{obj.slug}'

    # BÜYÜK SEO DOKUNUŞU: Google'a son güncellenme tarihini veriyoruz
    def lastmod(self, obj):
        return obj.updated_at