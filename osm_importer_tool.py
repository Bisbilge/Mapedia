import os
import django
import requests
from decimal import Decimal

# 1. DJANGO AYARLARI (Proje adınıza göre config.settings kısmını güncelleyin)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from django.utils.text import slugify
from apps.venues.models import Venue, VenueCategory, VenueContributor
from apps.categories.models import Category, FieldDefinition, FieldValue

# ==========================================
# 2. DEĞİŞKENLERİ BURADAN GÜNCELLEYİN
# ==========================================
TARGET_CATEGORY_ID = 12          # Kütüphane kategori ID'niz
OSM_TAG_KEY = "amenity"          # OSM anahtarı
OSM_TAG_VALUE = "library"        # OSM değeri
CITY_FILTER = "Istanbul"         # Şehir filtresi (Boş bırakırsanız Türkiye geneli arar)
BOT_USERNAME = "osm_bot"         # Katkıcı olarak atanacak kullanıcı adı

# Alan eşleştirmeleri (OSM Tag -> Mapedia Field Name)
# Örneğin OSM'deki 'opening_hours' bilgisini Mapedia'daki 'calisma-saatleri' alanına yazar.
FIELD_MAPPING = {
    "opening_hours": "opening-hours",
    "phone": "phone-number",
    "website": "website-url",
    # Buraya yeni field_definition name'lerini ekleyebilirsiniz
}

def get_osm_data():
    print(f"OSM'den {OSM_TAG_VALUE} verileri çekiliyor...")
    
    # Overpass Query
    area_filter = f'["addr:city"~"{CITY_FILTER}"]' if CITY_FILTER else ""
    query = f"""
    [out:json][timeout:25];
    node["{OSM_TAG_KEY}"="{OSM_TAG_VALUE}"]{area_filter}(39.0, 26.0, 42.0, 30.0);
    out body;
    """
    
    url = "https://overpass-api.de/api/interpreter"
    response = requests.get(url, params={'data': query})
    if response.status_code == 200:
        return response.json().get('elements', [])
    else:
        print("Hata: OSM verisi çekilemedi.")
        return []

def run_import():
    # Bot kullanıcısını al
    try:
        bot_user = User.objects.get(username=BOT_USERNAME)
    except User.DoesNotExist:
        print(f"Hata: {BOT_USERNAME} kullanıcısı bulunamadı!")
        return

    # Hedef kategoriyi al
    try:
        target_cat = Category.objects.get(id=TARGET_CATEGORY_ID)
    except Category.DoesNotExist:
        print(f"Hata: ID'si {TARGET_CATEGORY_ID} olan kategori bulunamadı!")
        return

    elements = get_osm_data()
    print(f"Toplam {len(elements)} öğe işlenecek.")

    for el in elements:
        tags = el.get('tags', {})
        name = tags.get('name') or tags.get('official_name') or f"Unnamed {OSM_TAG_VALUE}"
        lat = Decimal(str(el['lat']))
        lon = Decimal(str(el['lon']))
        
        # Mükerrer kontrolü (Aynı isim ve yakın koordinat)
        if Venue.objects.filter(name=name, city=CITY_FILTER).exists():
            continue

        # 1. Venue Oluştur
        venue = Venue.objects.create(
            name=name,
            slug=slugify(name) + "-" + str(el['id']),
            latitude=lat,
            longitude=lon,
            city=tags.get('addr:city', CITY_FILTER),
            country="Turkey",
            is_approved=True
        )

        # 2. VenueCategory İlişkisi
        vc = VenueCategory.objects.create(
            venue=venue,
            category=target_cat,
            is_approved=True
        )

        # 3. Katkıda Bulunan Ataması (osm_bot)
        VenueContributor.objects.create(
            venue=venue,
            user=bot_user,
            contribution_type='imported'
        )

        # 4. Özel Alanları (Field Values) Doldur
        for osm_key, mapedia_field_name in FIELD_MAPPING.items():
            val = tags.get(osm_key)
            if val:
                try:
                    f_def = FieldDefinition.objects.get(category=target_cat, name=mapedia_field_name)
                    FieldValue.objects.create(
                        venue_category=vc,
                        field=f_def,
                        value=val
                    )
                except FieldDefinition.DoesNotExist:
                    continue

        print(f"İçe aktarıldı: {name}")

if __name__ == "__main__":
    run_import()
    print("İşlem başarıyla tamamlandı.")