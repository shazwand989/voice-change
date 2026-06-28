from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view,   name='register'),
    path('login/',    views.login_view,       name='login'),
    path('logout/',   views.logout_view,      name='logout'),
    path('dashboard/', views.dashboard,       name='dashboard'),
    path('admin/',                      views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/',                views.user_list,       name='user_list'),
    path('admin/users/create/',         views.create_customer, name='create_customer'),
    path('admin/users/<int:user_id>/',  views.user_detail,     name='user_detail'),
]
