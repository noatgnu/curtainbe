# Generated by Django 5.1.4 on 2024-12-12 12:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curtain', '0010_alter_datacite_curtain'),
    ]

    operations = [
        migrations.AddField(
            model_name='datacite',
            name='lock',
            field=models.BooleanField(default=True),
        ),
    ]
