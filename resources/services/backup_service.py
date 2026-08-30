from .kubernetes_client import get_kubernetes_client
from ..models import BackupJob, PeriodicBackupJob, Status

from kubernetes import client
from kubernetes.stream import stream

import json
import base64
import shlex
from pathlib import Path
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django_celery_beat.models import (
    CrontabSchedule,
    PeriodicTask,
)


BACKUP_ROOT = Path("/backups")


def create_app_backup(backup):
    app = backup.app
    namespace = app.namespace.name

    api_client = get_kubernetes_client(app.namespace.cluster)
    core_v1 = client.CoreV1Api(api_client)

    pods = core_v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"app={app.name}",
        _request_timeout=(10, 30),
    ).items

    running_pod = next(
        (
            pod
            for pod in pods
            if pod.status.phase == "Running"
            and pod.status.pod_ip
        ),
        None
    )

    if running_pod is None:
        raise RuntimeError(f"No running pod was found for app '{app.name}'.")

    remote_command = ["sh", "-c", f"tar -czf - -- {shlex.quote(backup.source_path)} | base64",]
    archive_base64 = stream(
        core_v1.connect_get_namespaced_pod_exec,
        running_pod.metadata.name,
        namespace,
        command=remote_command,
        stdin=False,
        stdout=True,
        stderr=False,
        tty=False,
    )

    if not archive_base64:
        raise RuntimeError("The backup cammand returned no archive data.")

    backup_dir = (
        BACKUP_ROOT
        / str(app.id)
        / timezone.localdate().isoformat()
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    output_path = backup_dir / f"{backup.id}.tar.gz"

    try:
        archive_bytes = base64.b64decode(archive_base64)
    except Exception as e:
        raise RuntimeError("Could not decode the archive returned by the pod.") from e

    output_path.write_bytes(archive_bytes)
    return output_path

def create_periodic_schedule(periodic):
    parts = periodic.schedule.split()

    minute, hour, day_of_month, month_of_year, day_of_week = parts
    cron_schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
        timezone=settings.TIME_ZONE,
    )

    beat_task = PeriodicTask.objects.create(
        name=f"periodic-backup-{periodic.pk}",
        task="resources.tasks.trigger_periodic_backup",
        crontab=cron_schedule,
        args=json.dumps([periodic.pk]),
    )

    periodic.beat_task = beat_task
    periodic.save(update_fields=["beat_task"])

def queue_backup(app, source_path, periodic=None):
    with transaction.atomic():
        backup = BackupJob.objects.create(
            app=app, 
            source_path=source_path,
            status=Status.PENDING,
        )

        if periodic is not None:
            PeriodicBackupJob.objects.create(
                backup_job=backup,
                periodic=periodic,
            )

    def send_to_celery():
        from ..tasks import build_backup

        build_backup.delay(backup.pk)

    transaction.on_commit(send_to_celery)

    return backup