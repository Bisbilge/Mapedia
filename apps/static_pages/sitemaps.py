from django.contrib.sitemaps import Sitemap
from django.utils import timezone


class StaticPagesSitemap(Sitemap):
    changefreq = "monthly"

    # List of (path, priority) tuples for important static pages
    _pages = [
        ('/', 0.8),
        ('/about', 0.6),
        ('/categories', 0.7),
        ('/license', 0.5),
    ]

    def items(self):
        return self._pages

    def location(self, item):
        return item[0]

    def priority(self, item):
        return item[1]

    def lastmod(self, item):
        return timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
