from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/accounts/', include('accounts.user_urls')),
    path('api/v1/schools/', include('schools.urls')),
    path('api/v1/platform/', include('schools.platform_urls')),
    path('api/v1/', include('records.urls')),
]
