import uuid

from django.db import migrations, models


def backfill_public_ids(apps, schema_editor):
    """Give every existing row a unique public id before the column is unique.

    A single callable default on `AddField` would be evaluated once and stamp
    the same UUID on every existing row; assigning per row here avoids that.
    """
    for model_name in ('Student', 'StaffMember'):
        Model = apps.get_model('records', model_name)
        for pk in Model.objects.filter(public_id__isnull=True).values_list('pk', flat=True):
            Model.objects.filter(pk=pk).update(public_id=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0016_academicsession_term_end_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='public_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='staffmember',
            name='public_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='student',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='staffmember',
            name='public_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
