from django.urls import path
from . import views

app_name = 'packages'

urlpatterns = [
    path('',                       views.package_list,   name='list'),
    path('create/',                views.package_create, name='create'),
    path('<int:pkg_id>/edit/',     views.package_edit,   name='edit'),
    path('<int:pkg_id>/delete/',   views.package_delete, name='delete'),
]
