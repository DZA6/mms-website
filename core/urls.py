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
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload_photo, name='upload'),
    path('order/<str:tier>/', views.create_order, name='create_order'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('order/<int:order_id>/success/', views.order_success, name='order_success'),
    path('download/<int:slideshow_id>/<str:file_type>/', views.download_slideshow_file, name='download_file'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/add/<str:tier>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/checkout/', views.checkout_cart, name='checkout_cart'),
]

# Serve static and media files directly from Django.
# (Production: PythonAnywhere static mappings were unreliable for this
# site; Django serving from STATIC_ROOT/MEDIA_ROOT is the fallback.)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
