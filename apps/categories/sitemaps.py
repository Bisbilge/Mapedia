from django.contrib.sitemaps import Sitemap
from .models import Category

class CategorySitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        # Sadece aktif kategorileri getir
        return Category.objects.filter(is_active=True)

    def location(self, obj):
        return f'/category/{obj.slug}'

    # BÜYÜK SEO DOKUNUŞU: Kategori en son ne zaman güncellendi?
    def lastmod(self, obj):
        return obj.updated_at