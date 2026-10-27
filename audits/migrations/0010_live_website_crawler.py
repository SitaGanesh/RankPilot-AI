# Generated for live multi-agent website audit and browser observation
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0009_hypothesis_investigation_investigationaction_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='audit',
            name='audit_type',
            field=models.CharField(choices=[('page', 'Single page'), ('website', 'Full website')], default='website', max_length=16),
        ),
        migrations.AddField(
            model_name='audit',
            name='max_crawl_pages',
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.AddField(
            model_name='audit',
            name='max_crawl_depth',
            field=models.PositiveIntegerField(default=2),
        ),
        migrations.AddField(
            model_name='audit',
            name='same_domain_only',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='audit',
            name='pages_crawled_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddIndex(
            model_name='audit',
            index=models.Index(fields=['audit_type', 'status'], name='audits_audi_audit_t_f98c77_idx'),
        ),
        migrations.AlterField(
            model_name='crawlurl',
            name='status',
            field=models.CharField(choices=[
                ('discovered', 'Discovered'),
                ('queued', 'Queued'),
                ('processing', 'Processing'),
                ('completed', 'Completed'),
                ('failed', 'Failed'),
                ('skipped', 'Skipped'),
                ('pending', 'Pending'),
                ('fetching', 'Fetching'),
                ('fetched', 'Fetched'),
            ], default='queued', max_length=16),
        ),
        migrations.AddField(
            model_name='crawlurl',
            name='deeply_audited',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='crawlurl',
            name='timing_ms',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='crawlurl',
            name='content_type',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='crawlurl',
            name='page_title',
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name='crawlurl',
            name='browser_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddIndex(
            model_name='crawlurl',
            index=models.Index(fields=['audit', 'status'], name='audits_craw_audit_i_07b1d1_idx'),
        ),
        migrations.AddIndex(
            model_name='crawlurl',
            index=models.Index(fields=['audit', 'deeply_audited'], name='audits_craw_audit_i_c01999_idx'),
        ),
        migrations.CreateModel(
            name='AuditLiveEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(blank=True, max_length=2048)),
                ('event_type', models.CharField(db_index=True, max_length=50)),
                ('data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('audit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_events', to='audits.audit')),
            ],
            options={
                'ordering': ['id'],
                'indexes': [
                    models.Index(fields=['audit', 'id'], name='audits_audi_audit_i_413e16_idx'),
                    models.Index(fields=['audit', 'event_type'], name='audits_audi_audit_i_653d9e_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='PageAuditReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=2048)),
                ('normalized_url', models.URLField(db_index=True, max_length=2048)),
                ('title', models.CharField(blank=True, max_length=512)),
                ('status_code', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('report_json', models.JSONField(default=dict)),
                ('browser_data', models.JSONField(blank=True, default=dict)),
                ('score_percent', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('audit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='page_reports', to='audits.audit')),
                ('crawl_url', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='page_reports', to='audits.crawlurl')),
            ],
            options={
                'ordering': ['created_at', 'id'],
                'constraints': [
                    models.UniqueConstraint(fields=('audit', 'normalized_url'), name='unique_page_report_per_audit_url'),
                ],
            },
        ),
    ]
