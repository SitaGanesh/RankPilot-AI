from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audits", "0013_rename_audits_audi_audit_i_seq_idx_audits_audi_audit_i_4e5535_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="audit",
            name="crawl_stats",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Observed crawl counters (discovered, queued, attempted, fetched, failed, shallow checks, unique resources).",
            ),
        ),
        migrations.AddField(
            model_name="crawllink",
            name="anchor_text",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="crawllink",
            name="raw_href",
            field=models.CharField(blank=True, max_length=2048),
        ),
        migrations.AddField(
            model_name="crawllink",
            name="rel",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="crawllink",
            name="section",
            field=models.CharField(
                blank=True,
                help_text="DOM region the link was found in (header, nav, footer, main ...).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="crawllink",
            name="discovered_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
