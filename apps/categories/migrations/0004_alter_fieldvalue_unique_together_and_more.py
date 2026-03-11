import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('categories', '0003_category_moderators_category_owner'),
        ('venues', '0005_remove_historicalvenue_address_and_more'),
    ]
    operations = [
        migrations.AlterUniqueTogether(
            name='fieldvalue',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='fieldvalue',
            name='venue_category',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='field_values', to='venues.venuecategory', verbose_name='Venue Category'),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='fieldvalue',
            name='venue',
        ),
        migrations.AlterUniqueTogether(
            name='fieldvalue',
            unique_together={('venue_category', 'field')},
        ),
    ]
