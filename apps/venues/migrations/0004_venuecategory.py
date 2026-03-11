from django.db import migrations, models
import django.db.models.deletion


def migrate_fk_to_venuecategory(apps, schema_editor):
    Venue = apps.get_model('venues', 'Venue')
    VenueCategory = apps.get_model('venues', 'VenueCategory')
    for venue in Venue.objects.filter(category__isnull=False):
        VenueCategory.objects.get_or_create(
            venue=venue,
            category=venue.category,
            defaults={'is_approved': venue.is_approved},
        )


def migrate_fk_to_venuecategory_reverse(apps, schema_editor):
    Venue = apps.get_model('venues', 'Venue')
    VenueCategory = apps.get_model('venues', 'VenueCategory')
    for vc in VenueCategory.objects.select_related('venue', 'category'):
        Venue.objects.filter(pk=vc.venue_id).update(category=vc.category)


class Migration(migrations.Migration):

    dependencies = [
        ('venues', '0003_historicalvenue_map_url_venue_map_url'),
        ('categories', '0003_category_moderators_category_owner'),
    ]

    operations = [
        migrations.CreateModel(
            name='VenueCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_approved', models.BooleanField(default=False, verbose_name='Approved')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='venue_categories',
                    to='categories.category',
                )),
                ('venue', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='venue_categories',
                    to='venues.venue',
                )),
            ],
            options={
                'verbose_name': 'Venue Category',
                'verbose_name_plural': 'Venue Categories',
                'unique_together': {('venue', 'category')},
            },
        ),
        migrations.RunPython(
            migrate_fk_to_venuecategory,
            migrate_fk_to_venuecategory_reverse,
        ),
        migrations.RemoveField(model_name='venue', name='category'),
        migrations.RemoveField(model_name='venue', name='address'),
        migrations.RemoveField(model_name='venue', name='map_url'),
    ]
