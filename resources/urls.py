from django.urls import path
from . import views

urlpatterns = [
    path("clusters/", views.ClusterCreate.as_view()),

    path("namespaces/", views.NamespaceCreate.as_view()),
    path("namespace/get/<int:id>/", views.RetrieveNamespace.as_view()),
    path("namespace/delete/<int:id>/", views.NamespaceDelete.as_view()),

    path("app/", views.AppListCreate.as_view()),
    path("app/update/<int:id>/", views.AppUpdate.as_view()),
    path("app/delete/<int:id>/", views.AppDelete.as_view()),

    path("backup/", views.BackupCreate.as_view()),
    path("backup/<str:backup_id>/", views.RetrieveBackup.as_view()),
    path("backup/app/<int:app_id>/", views.BackupAppList.as_view()),
    path("periodic-backup/", views.PeriodicBackupCreate.as_view()),
    path("periodic-backup/<str:backup_id>", views.RetrievePeriodicBackup.as_view()),
]