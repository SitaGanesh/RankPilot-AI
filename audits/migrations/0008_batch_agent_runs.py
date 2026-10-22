from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("audits", "0007_batch_crawling")]

    operations = [
        migrations.AddField(
            model_name="batchtarget",
            name="analysis_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("partial", "Partial"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="BatchAgentRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agent_id", models.CharField(max_length=100)),
                ("attempt", models.PositiveSmallIntegerField(default=1)),
                ("status", models.CharField(choices=[("running", "Running"), ("completed", "Completed"), ("partial", "Partial"), ("failed", "Failed")], max_length=12)),
                ("result_json", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True)),
                ("finding_keys", models.JSONField(default=list)),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_runs", to="audits.batchtarget")),
            ],
            options={"ordering": ["agent_id"]},
        ),
        migrations.AddConstraint(
            model_name="batchagentrun",
            constraint=models.UniqueConstraint(
                fields=("target", "agent_id"), name="unique_batch_target_agent"
            ),
        ),
    ]
