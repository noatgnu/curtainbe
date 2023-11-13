# Generated by Django 4.2.7 on 2023-11-13 12:06

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('curtain', '0002_remove_curtain_md5_datahash_dataaesencryptionfactors'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='curtain',
            name='encrypted_with',
        ),
        migrations.AddField(
            model_name='dataaesencryptionfactors',
            name='encrypted_with',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encrypted_with', to='curtain.userpublickey'),
        ),
    ]
