from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("audits", "0006_audit_skip_discovery")]

    operations = [
        migrations.CreateModel(
            name="AuditBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("partial", "Partial"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending", max_length=12)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("completed_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("allow_internal_discovery", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BatchTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField()),
                ("submitted_url", models.URLField(max_length=2048)),
                ("normalized_url", models.URLField(max_length=2048)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("retryable", "Retryable"), ("completed", "Completed"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=12)),
                ("final_url", models.URLField(blank=True, max_length=2048)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("content_type", models.CharField(blank=True, max_length=255)),
                ("timing_ms", models.FloatField(blank=True, null=True)),
                ("html", models.BooleanField(default=False)),
                ("image_count", models.PositiveIntegerField(default=0)),
                ("internal_link_count", models.PositiveIntegerField(default=0)),
                ("external_link_count", models.PositiveIntegerField(default=0)),
                ("broken_link_count", models.PositiveIntegerField(default=0)),
                ("evidence", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="targets", to="audits.auditbatch")),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddConstraint(model_name="batchtarget", constraint=models.UniqueConstraint(fields=("batch", "normalized_url"), name="unique_batch_target_url")),
        migrations.AddConstraint(model_name="batchtarget", constraint=models.UniqueConstraint(fields=("batch", "position"), name="unique_batch_target_position")),
    ]
