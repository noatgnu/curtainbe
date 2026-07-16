from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('curtain', '0021_add_name_field_to_curtain'),
    ]

    operations = [
        migrations.AddField(
            model_name='datacite',
            name='error_message',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='datacite',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('published', 'Published'),
                    ('draft', 'Draft'),
                    ('rejected', 'Rejected'),
                    ('error', 'Error'),
                ],
                default='pending',
                max_length=10,
            ),
        ),
    ]