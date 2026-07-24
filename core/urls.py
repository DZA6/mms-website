from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from main import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('memorial-admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('pricing/', views.pricing_page, name='pricing'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.custom_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload_photo, name='upload'),
    path('order/<str:tier>/', views.create_order, name='create_order'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
