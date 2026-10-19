from django.db import migrations


def classify_existing_non_html(apps, schema_editor):
    CrawlURL = apps.get_model("audits", "CrawlURL")
    CrawlURL.objects.filter(error="Response Content-Type is not HTML").update(
        resource_type="media",
        status="skipped",
        error="Non-HTML resource (content type was not retained)",
    )


class Migration(migrations.Migration):
    dependencies = [("audits", "0004_crawlurl_resource_type")]

    operations = [migrations.RunPython(classify_existing_non_html, migrations.RunPython.noop)]
