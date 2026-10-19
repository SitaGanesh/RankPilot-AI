from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("audits", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="CrawlURL",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField(max_length=2048)),
                ("depth", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("fetching", "Fetching"), ("fetched", "Fetched"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=10)),
                ("final_url", models.URLField(blank=True, max_length=2048)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("audit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="crawl_urls", to="audits.audit")),
                ("discovered_from", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="discovered_urls", to="audits.crawlurl")),
            ],
            options={"ordering": ["depth", "created_at", "id"]},
        ),
        migrations.CreateModel(
            name="CrawlLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="crawl_links", to="audits.audit")),
                ("destination", models.ForeignKey(on_delete=django.db.models.CASCADE, related_name="incoming_links", to="audits.crawlurl")),
                ("source", models.ForeignKey(on_delete=django.db.models.CASCADE, related_name="outgoing_links", to="audits.crawlurl")),
            ],
        ),
        migrations.AddConstraint(
            model_name="crawlurl",
            constraint=models.UniqueConstraint(fields=("audit", "url"), name="unique_crawl_url_per_audit"),
        ),
        migrations.AddConstraint(
            model_name="crawllink",
            constraint=models.UniqueConstraint(fields=("audit", "source", "destination"), name="unique_crawl_link_per_audit"),
        ),
    ]
