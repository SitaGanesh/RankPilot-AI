from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audits", "0002_crawldiscovery")]

    operations = [
        migrations.AddField(
            model_name="crawlurl",
            name="discovery_source",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("internal_link", "Internal link"),
                    ("sitemap", "Sitemap"),
                ],
                default="submitted",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="crawlurl",
            name="discovery_source_url",
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]
