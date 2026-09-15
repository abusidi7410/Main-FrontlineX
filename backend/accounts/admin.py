from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = [
        'email', 'first_name', 'last_name', 'role',
        'school', 'is_verified', 'is_active',
    ]
    list_filter = ['role', 'is_verified', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'phone']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('email', 'phone', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Role & school', {'fields': ('role', 'school')}),
        ('Permissions', {
            'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser',
                        'groups', 'user_permissions'),
        }),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'phone', 'first_name', 'last_name',
                'role', 'school', 'password1', 'password2',
                'is_active', 'is_staff',
            ),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')
