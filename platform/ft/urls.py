from django.urls import path
from django.views.static import serve
from django.conf import settings
from core import api

urlpatterns = [
 path('',api.index),
 path('api/session',api.session), path('api/setup',api.setup),
 path('api/login',api.signin),path('api/logout',api.signout),path('api/password',api.password),
 path('api/data',api.snapshot),path('api/records/<str:kind>',api.record),path('api/records/<str:kind>/<int:pk>',api.record),
 path('api/users',api.users),path('api/users/<int:pk>',api.users),
 path('api/inventory',api.inventory),path('api/versions',api.upload_version),path('api/versions/<int:pk>/status',api.version_status),
 path('api/tasks/<int:pk>/updates',api.progress),path('api/files/<str:kind>/<int:pk>',api.download),path('api/export/<str:kind>',api.export_csv),
 path('static/<path:path>',serve,{'document_root':settings.BASE_DIR/'static'}),
]
