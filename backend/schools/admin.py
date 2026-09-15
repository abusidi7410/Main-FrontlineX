from django.contrib import admin
from .models import School, SubscriptionPlan, SchoolSubscription


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'school_type', 'state', 'lga', 'is_active', 'created_at']
    list_filter = ['school_type', 'state', 'is_active']
    search_fields = ['name', 'email']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'min_students', 'max_students',
        'monthly_price', 'ai_credits', 'is_active',
    ]


@admin.register(SchoolSubscription)
class SchoolSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['school', 'plan', 'status', 'starts_at', 'expires_at']
    list_filter = ['status']
