from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audits", "0005_classify_existing_non_html")]

    operations = [
        migrations.AddField(
            model_name="audit",
            name="skip_discovery",
            field=models.BooleanField(
                default=False,
                help_text="When true, collection fetches only the submitted URL and does not crawl the site.",
            ),
        ),
    ]
