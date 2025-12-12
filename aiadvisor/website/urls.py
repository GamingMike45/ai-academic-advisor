from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# Create your URLs here.

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='website/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload_transcript/', views.upload_transcript, name='upload_transcript'),
    path('settings/', views.user_settings, name='settings'),
    path('chat/', views.chat_page, name='chat_page'),
    path('chat/send/', views.send_message, name='send_message'),
    path('chat/clear/', views.clear_chat, name='clear_chat'),
    path('chat/export/pdf/', views.export_chat_pdf, name='export_chat_pdf'),
]