import uuid
from django.db import models
from django_celery_beat.models import PeriodicTask

class Cluster(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    token = models.TextField()

    def __str__(self):
        return self.name


class NamespaceStatus(models.TextChoices):
    READY = "ready"
    TERMINATING = "terminating"
    DELETED = "deleted"

class Namespace(models.Model):
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=NamespaceStatus.choices, default=NamespaceStatus.READY)

    def __str__(self):
        return self.name


class DeletionStatus(models.TextChoices):
    NOT_DELETED = "not-deleted", "Not Deleted"
    TERMINATING = "terminating", "Terminating"

class App(models.Model):
    name = models.CharField(max_length=100)

    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name="apps")
    image = models.CharField(max_length=255)
    deletion_status = models.CharField(max_length=20, choices=DeletionStatus.choices, default=DeletionStatus.NOT_DELETED)

    replicas = models.PositiveBigIntegerField(default=1)

    container_port = models.PositiveIntegerField(null=True, blank=True)

    cpu_request = models.CharField(max_length=20, blank=True)
    cpu_limit = models.CharField(max_length=20, blank=True)
    memory_request = models.CharField(max_length=20, blank=True)
    memory_limit = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Status(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"

def generate_backup_id():
    return f"bkp_{uuid.uuid4().hex[:6]}"

class BackupJob(models.Model):
    backup_id = models.CharField(max_length=10, unique=True, default=generate_backup_id, editable=False)

    app = models.ForeignKey(App, on_delete=models.PROTECT)
    source_path = models.TextField(max_length=250)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(max_length=250, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class PeriodicBackup(models.Model):
    app = models.ForeignKey(App, on_delete=models.CASCADE)
    source_path = models.TextField(max_length=250)
    schedule = models.CharField(max_length=100)

    beat_task = models.OneToOneField(PeriodicTask, null=True, blank=True, on_delete=models.SET_NULL,)

    created_at = models.DateTimeField(auto_now_add=True)

class PeriodicBackupJob(models.Model):
    backup_job = models.OneToOneField(BackupJob, on_delete=models.CASCADE)
    periodic = models.ForeignKey(PeriodicBackup, null=True, on_delete=models.SET_NULL)