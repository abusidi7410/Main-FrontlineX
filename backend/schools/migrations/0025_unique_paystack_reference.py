# Concurrency hardening: the gateway reference is the webhook's join key and
# must be unique when present, so a callback can never match two payments.
# Blank (not yet initialised) rows are excluded via the partial index.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0024_default_override_note'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='subscriptionpayment',
            constraint=models.UniqueConstraint(
                condition=~models.Q(paystack_reference=''),
                fields=('paystack_reference',),
                name='unique_subscription_paystack_reference',
            ),
        ),
    ]
