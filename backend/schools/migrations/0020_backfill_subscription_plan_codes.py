"""Give every existing plan a stable `code` and a display order.

The `code` is the identifier the frontend stores and re-sends (e.g. ``t400``),
so a plan can be renamed without orphaning the schools pointing at it. It has to
be backfilled before the column is treated as meaningful. No plan rows are
created here: an operator's own plans are left exactly as they are.
"""
import re

from django.db import migrations


def _slug_like(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z0-9_-]+', value or ''))


def backfill(apps, schema_editor):
    SubscriptionPlan = apps.get_model('schools', 'SubscriptionPlan')
    for plan in SubscriptionPlan.objects.filter(code__isnull=True).order_by('id'):
        base = plan.name if _slug_like(plan.name) else f't{plan.min_students}'
        base = (base or f't{plan.min_students}')[:40]
        code = base
        suffix = 1
        while SubscriptionPlan.objects.filter(code=code).exclude(pk=plan.pk).exists():
            suffix += 1
            code = f'{base[:36]}-{suffix}'
        updates = ['code']
        plan.code = code
        if not plan.sort_order:
            plan.sort_order = plan.min_students
            updates.append('sort_order')
        plan.save(update_fields=updates)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0019_alter_subscriptionplan_options_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
