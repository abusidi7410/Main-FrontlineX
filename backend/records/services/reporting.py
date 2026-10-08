"""Profit/cost reporting built on the centralized usage ledger.

The platform's variable cost per school is exactly what the ledger recorded:
every SMS, OTP and AI unit a school consumed, priced at the school's plan
costs. Revenue side is the subscription price. Gross margin is the difference.

Money units follow the codebase convention: revenue in naira (Decimal),
ledger costs in kobo (integer). `cost_naira` divides kobo by 100; the
response serializers round to 2 places so the frontend never sees float dust.
"""

from datetime import datetime
from decimal import Decimal

from django.db.models import Case, F, IntegerField, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from records.models import UsageRecord
from schools.models import School, SchoolSubscription

# A unit's ledger cost is what the provider actually reported; when the
# provider reports nothing (console provider, provider outage) fall back to
# the plan's estimated per-unit cost so margin estimation never silently
# reads zero.
_ACTUAL_OR_ESTIMATED = Case(
    When(actual_cost__gt=0, then=F('actual_cost')),
    default=Coalesce(F('estimated_cost'), Value(0)),
    output_field=IntegerField(),
)

RESOURCE_TYPES = (
    UsageRecord.ResourceType.SMS,
    UsageRecord.ResourceType.OTP,
    UsageRecord.ResourceType.AI,
)

_STATUS_SUCCEEDED = UsageRecord.Status.SUCCEEDED
_STATUS_FAILED = UsageRecord.Status.FAILED
_STATUS_EXHAUSTED = UsageRecord.Status.EXHAUSTED


def month_window(year: int, month: int) -> tuple:
    """Half-open [start, end) window for one calendar month, timezone-aware."""
    start = timezone.make_aware(
        datetime(year, month, 1),
        timezone.get_current_timezone(),
    )
    if month == 12:
        end = timezone.make_aware(
            datetime(year + 1, 1, 1),
            timezone.get_current_timezone(),
        )
    else:
        end = timezone.make_aware(
            datetime(year, month + 1, 1),
            timezone.get_current_timezone(),
        )
    return start, end


def current_month_key() -> tuple:
    today = timezone.localdate()
    return today.year, today.month


def parse_month_param(value) -> tuple:
    """Parse 'YYYY-MM' into (year, month); empty means the current month."""
    if not value:
        return current_month_key()
    try:
        year_str, month_str = value.split('-', 1)
        year, month = int(year_str), int(month_str)
    except ValueError:
        raise ValueError("Expected a month as 'YYYY-MM'.")
    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        raise ValueError("Expected a month as 'YYYY-MM'.")
    return year, month


def usage_costs_for(school_ids, start, end) -> dict:
    """Aggregate the ledger for the given schools over [start, end).

    One grouped query regardless of school count, pivoted in Python into
    ``{school_id: {resource: stats}}``. Schools with no rows get an entry
    with zeros so callers never have to guard for missing keys.
    """
    rows = (
        UsageRecord.objects.filter(
            school_id__in=school_ids,
            created_at__gte=start,
            created_at__lt=end,
        )
        .values('school_id', 'resource_type', 'status')
        .annotate(
            quantity=Sum('quantity'),
            credits=Sum('credits_used'),
            cost=Sum(_ACTUAL_OR_ESTIMATED),
        )
    )

    report = {
        school_id: {
            resource: {
                'attempted': 0,
                'succeeded': 0,
                'failed': 0,
                'blocked': 0,
                'quantity': 0,
                'credits': 0,
                'costKobo': 0,
            }
            for resource in RESOURCE_TYPES
        }
        for school_id in school_ids
    }

    for row in rows:
        stats = report[row['school_id']][row['resource_type']]
        quantity = row['quantity'] or 0
        stats['attempted'] += quantity
        stats['quantity'] += quantity
        stats['credits'] += row['credits'] or 0
        stats['costKobo'] += row['cost'] or 0
        if row['status'] == _STATUS_SUCCEEDED:
            stats['succeeded'] += quantity
        elif row['status'] == _STATUS_FAILED:
            stats['failed'] += quantity
        elif row['status'] == _STATUS_EXHAUSTED:
            stats['blocked'] += quantity

    return report


def _cost_naira(cost_kobo: int) -> Decimal:
    return (Decimal(cost_kobo) / Decimal(100)).quantize(Decimal('0.01'))


def _margin_percent(revenue: Decimal, cost: Decimal):
    if revenue <= 0:
        return None
    return float(((revenue - cost) / revenue * 100).quantize(Decimal('0.1')))


def school_report(school, start, end) -> dict:
    """One school's subscription revenue vs paid-service cost for a window."""
    subscription = (
        SchoolSubscription.objects.filter(school=school)
        .select_related('plan')
        .first()
    )
    plan = subscription.plan if subscription and subscription.plan_id else None
    usage = usage_costs_for([school.id], start, end)[school.id]

    for resource in RESOURCE_TYPES:
        stats = usage[resource]
        stats['costNaira'] = _cost_naira(stats['costKobo'])
        if resource == UsageRecord.ResourceType.SMS:
            allowance = plan.monthly_sms_allowance if plan else 0
        elif resource == UsageRecord.ResourceType.OTP:
            allowance = plan.monthly_otp_allowance if plan else 0
        else:
            allowance = plan.monthly_ai_allowance if plan else 0
        # Attempted (not succeeded) units count against the allowance: a
        # blocked send must still consume budget or exhaustion is toothless.
        stats['allowance'] = allowance
        stats['remaining'] = max(allowance - stats['attempted'], 0)

    revenue = plan.monthly_price if plan else Decimal('0')
    cost = _cost_naira(
        sum(usage[resource]['costKobo'] for resource in RESOURCE_TYPES)
    )
    margin = (revenue - cost).quantize(Decimal('0.01'))

    return {
        'plan': (
            {
                'name': plan.name,
                'monthlyPrice': plan.monthly_price,
                'smsAllowance': plan.monthly_sms_allowance,
                'otpAllowance': plan.monthly_otp_allowance,
                'aiAllowance': plan.monthly_ai_allowance,
                'smsCostPerUnitKobo': plan.sms_cost_per_unit,
                'otpCostPerUnitKobo': plan.otp_cost_per_unit,
                'aiCostPerCreditKobo': plan.ai_cost_per_credit,
            }
            if plan
            else None
        ),
        'subscriptionStatus': subscription.status if subscription else None,
        'usage': usage,
        'revenueNaira': revenue,
        'costNaira': cost,
        'grossMarginNaira': margin,
        'grossMarginPercent': _margin_percent(revenue, cost),
    }


def platform_profit_report(start, end) -> dict:
    """Every school as a P&L row: subscription revenue vs variable cost."""
    subscriptions = (
        SchoolSubscription.objects.select_related('plan', 'school')
        .order_by('school__name')
    )
    by_school = {sub.school_id: sub for sub in subscriptions}
    # Schools appear if they have a subscription OR spent anything in the
    # window: a school with cost and no subscription is the worst margin
    # case and must not be invisible.
    spent_ids = set(
        UsageRecord.objects.filter(
            created_at__gte=start, created_at__lt=end,
        ).values_list('school_id', flat=True)
    )
    school_ids = list(set(by_school) | spent_ids)

    usage = usage_costs_for(school_ids, start, end)

    rows = []
    totals_revenue = Decimal('0')
    totals_cost = Decimal('0')
    active_count = 0

    # Schools without a subscription row still appear (cost with no revenue
    # is the worst margin case and must not be invisible).
    schools = School.objects.filter(id__in=set(school_ids) | {
        sid for sid, stats in usage.items()
        if any(stats[r]['attempted'] for r in RESOURCE_TYPES)
    }).order_by('name')

    for school in schools:
        subscription = by_school.get(school.id)
        plan = subscription.plan if subscription and subscription.plan_id else None
        stats = usage.get(school.id) or {
            resource: {
                'attempted': 0, 'succeeded': 0, 'failed': 0, 'blocked': 0,
                'quantity': 0, 'credits': 0, 'costKobo': 0,
            }
            for resource in RESOURCE_TYPES
        }

        cost = _cost_naira(
            sum(stats[resource]['costKobo'] for resource in RESOURCE_TYPES)
        )
        revenue = plan.monthly_price if plan else Decimal('0')
        if plan and subscription and subscription.status == 'active':
            active_count += 1
        margin = (revenue - cost).quantize(Decimal('0.01'))
        totals_revenue += revenue
        totals_cost += cost

        rows.append({
            'schoolId': str(school.id),
            'schoolName': school.name,
            'subscriptionStatus': subscription.status if subscription else None,
            'planName': plan.name if plan else None,
            'revenueNaira': revenue,
            'costNaira': cost,
            'grossMarginNaira': margin,
            'grossMarginPercent': _margin_percent(revenue, cost),
            'usage': stats,
        })

    total_margin = (totals_revenue - totals_cost).quantize(Decimal('0.01'))
    return {
        'totals': {
            'schools': len(rows),
            'activeSubscriptions': active_count,
            'revenueNaira': totals_revenue,
            'costNaira': totals_cost,
            'grossMarginNaira': total_margin,
            'grossMarginPercent': _margin_percent(totals_revenue, totals_cost),
        },
        'schools': rows,
    }
