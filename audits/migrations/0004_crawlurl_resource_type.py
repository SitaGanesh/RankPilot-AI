from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audits", "0003_crawlurl_provenance")]

    operations = [
        migrations.AddField(
            model_name="crawlurl",
            name="resource_type",
            field=models.CharField(
                choices=[("page", "HTML page"), ("media", "Media resource")],
                default="page",
                max_length=10,
            ),
        ),
    ]
