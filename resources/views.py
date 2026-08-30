from django.db import transaction
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveAPIView, 
    DestroyAPIView, 
    RetrieveUpdateAPIView, 
    CreateAPIView, 
    ListAPIView
)
from rest_framework.response import Response
from rest_framework import status
from kubernetes.client.exceptions import ApiException
from .tasks import build_backup

from . models import Cluster, Namespace, App, NamespaceStatus, DeletionStatus, BackupJob, PeriodicBackupJob
from .serializers import (
    ClusterSerializer, 
    NamespaceSerializer, 
    AppSerializer, 
    AppUpdateSerializer, 
    BackupAppListSerializer, 
    BackupSerializer,
    PeriodicBackupSerializer
)

from .services.kuber_service import (
    create_kuber_namespace, 
    delete_kuber_namespace, 
    create_app_deployment, 
    get_app_status, 
    update_app_deployment, 
    delete_kuber_app,
)
from .services.backup_service import create_periodic_schedule

class ClusterCreate(ListCreateAPIView):
    queryset = Cluster.objects.all()
    serializer_class = ClusterSerializer



class NamespaceCreate(ListCreateAPIView):
    queryset = Namespace.objects.all()
    serializer_class = NamespaceSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)


        namespace_name = serializer.validated_data["name"]
        cluster = serializer.validated_data["cluster"]

        try:
            create_kuber_namespace(cluster, namespace_name)
        except ApiException as e:
            if e.status == 400:
                return Response(
                    {"error": "Invalid Kubernetes request."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if e.status == 401:
                return Response(
                    {"error": "Kubernetes authentication faild."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            if e.status == 403:
                return Response(
                    {"error": "Permission denied by Kubernetes."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if e.status == 404:
                return Response(
                    {"error": "Kubernetes resource not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if e.status == 409:
                return Response(
                    {"error": "Namespace already exists."},
                    status=status.HTTP_409_CONFLICT
                )
            return Response(
                {"error": "Error while connecting the Kubernetes."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

class RetrieveNamespace(RetrieveAPIView):
    queryset = Namespace.objects.all()
    serializer_class = NamespaceSerializer
    lookup_field = "id"

class NamespaceDelete(DestroyAPIView):
    queryset = Namespace.objects.all()
    serializer_class = NamespaceSerializer
    lookup_field = "id"

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        namespace_id = kwargs["id"]

        updated = Namespace.objects.filter(
            id=namespace_id,
            status="ready"
        ).update(status=NamespaceStatus.TERMINATING)

        if updated == 0:
            return Response(
                {"error": "Namespace is already being deleted or does not exist."},
                status=status.HTTP_409_CONFLICT
            )

        namespace = Namespace.objects.get(id=namespace_id)

        try:
            delete_kuber_namespace(namespace.cluster, namespace.name)

        except ApiException as e:
            if e.status != 404:
                namespace.status = "ready"
                namespace.save(update_fields=["status"])

                return Response(
                    {"error": "Could not delete namespace from Kubernetes."},
                    status=status.HTTP_502_BAD_GATEWAY
                )

        namespace.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )



class AppListCreate(ListCreateAPIView):
    queryset = App.objects.all()
    serializer_class = AppSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        namespace = serializer.validated_data["namespace"]

        app = App(
            name=serializer.validated_data["name"],
            namespace=namespace,
            image=serializer.validated_data["image"],
            replicas=serializer.validated_data.get("replicas", 1),
            container_port=serializer.validated_data.get("container_port"),
            cpu_request=serializer.validated_data.get("cpu_request", ""),
            cpu_limit=serializer.validated_data.get("cpu_limit", ""),
            memory_request=serializer.validated_data.get("memory_request", ""),
            memory_limit=serializer.validated_data.get("memory_limit", ""),
        )

        try:
            create_app_deployment(app)

        except ApiException as e:
            print(e)
            print(e.body)
            if e.status == 400:
                return Response(
                    {"error": "Invalid Kubernetes request."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if e.status == 401:
                return Response(
                    {"error": "Kubernetes authentication failed."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if e.status == 403:
                return Response(
                    {"error": "Permission denied by Kubernetes."},
                    status=status.HTTP_403_FORBIDDEN
                )

            if e.status == 404:
                return Response(
                    {"error": "Namespace or Kubernetes resource not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            if e.status == 409:
                return Response(
                    {"error": "Deployment already exists."},
                    status=status.HTTP_409_CONFLICT
                )

            return Response(
                {"error": "kubernetes API error."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    def list(self, request, *args, **kwargs):
        apps = self.get_queryset()

        response_data = []

        for app in apps:
            app_data = AppSerializer(app).data
            live_status = get_app_status(app)
            app_data.update(live_status)
            response_data.append(app_data)
        return Response(response_data)



class AppUpdate(RetrieveUpdateAPIView):
    queryset = App.objects.all()
    serializer_class = AppUpdateSerializer
    lookup_field = "id"

    def perform_update(self, serializer):
        instance = self.get_object()

        try:
            update_app_deployment(
                instance,
                serializer.validated_data
            )
        except ApiException as e:
            if e.status == 404:
                return Response(
                    {"error": "Deployment not found in Kubernetes."},
                    status=status.HTTP_404_NOT_FOUND
                )

            if e.status == 403:
                return Response(
                    {"error": "Permission denied by Kubernetes."},
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response(
                {"error": "Could not update Kubernetes deployment."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

class AppDelete(DestroyAPIView):
    queryset = App.objects.all()
    serializer_class = AppSerializer
    lookup_field = "id"

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        app_id = kwargs["id"]

        updated = App.objects.filter(
            id=app_id,
            deletion_status=DeletionStatus.NOT_DELETED
        ).update(deletion_status=DeletionStatus.TERMINATING)

        if updated == 0:
            return Response(
                {"error": "App is already being deleted or does not exist."},
                status=status.HTTP_409_CONFLICT
            )

        app = App.objects.get(id=app_id)

        try:
            delete_kuber_app(app)

        except ApiException as e:
            if e.status == 404:
                app.delete()

                return Response(
                    status=status.HTTP_204_NO_CONTENT
                )

            App.objects.filter(id=app_id).update(
                deletion_status=DeletionStatus.NOT_DELETED
            )

            return Response(
                {"error": "Could not delete app from Kubernetes."},
                status=status.HTTP_502_BAD_GATEWAY
            )


        try:
            app.delete()
        except Exception:
            return Response(
                {"error": "App was deleted from Kubernetes, but database cleanup failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(    
            status=status.HTTP_204_NO_CONTENT
        )


class BackupCreate(ListCreateAPIView):
    serializer_class = BackupSerializer
    queryset = BackupJob.objects.all()
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = serializer.validated_data["app"]
        source_path = serializer.validated_data["source_path"]

        backup = BackupJob.objects.create(app=app, source_path=source_path)
        build_backup.delay(backup.id)

        return Response(
            {
                "backup_id": backup.id,
                "status": backup.status
            },
            status=status.HTTP_202_ACCEPTED
        )

class RetrieveBackup(RetrieveAPIView):
    serializer_class = BackupSerializer
    queryset = BackupJob.objects.all()
    lookup_field = "backup_id"
    
class BackupAppList(ListAPIView):
    serializer_class = BackupAppListSerializer

    def get_queryset(self):
        return BackupJob.objects.filter(
            app__id=self.kwargs["app_id"]
        ).order_by("status", "-created_at")

class PeriodicBackupCreate(ListCreateAPIView):
    serializer_class = PeriodicBackupSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        periodic = serializer.save()
        create_periodic_schedule(periodic)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

class RetrievePeriodicBackup(RetrieveAPIView):
    serializer_class = PeriodicBackupSerializer
    queryset = PeriodicBackupJob.objects.all()
    lookup_field = "backup_id"