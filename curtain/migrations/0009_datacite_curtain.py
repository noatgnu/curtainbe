# Generated by Django 5.1.4 on 2024-12-11 16:44

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curtain', '0008_remove_datacite_curtain_alter_datacite_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='datacite',
            name='curtain',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='data_cite', to='curtain.curtain'),
        ),
    ]
