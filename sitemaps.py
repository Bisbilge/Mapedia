# Her app'in içindeki sitemap sınıfını import ediyoruz
from apps.venues.sitemaps import VenueSitemap
from apps.categories.sitemaps import CategorySitemap
# Eğer diğer app'lerinde de (contributions, accounts) sitemap varsa onları da ekle

# Hepsini tek bir sözlükte topluyoruz
sitemaps = {
    'venues': VenueSitemap,
    'categories': CategorySitemap,
    # 'contributions': ContributionSitemap, # Varsa
}