import logging
from celery import shared_task
from .models import BackupJob, PeriodicBackup, Status
from .services.backup_service import create_app_backup, queue_backup

from django.utils import timezone
from django.db.models import Q

from datetime import timedelta


logger = logging.getLogger(__name__)


@shared_task(
    soft_time_limit=23 * 60 * 60,
    time_limit=24 * 60 * 60,
)
def build_backup(backup_id):
    backup = BackupJob.objects.select_related(
        "app__namespace__cluster"
    ).get(id=backup_id)

    try:
        backup.status = Status.RUNNING
        backup.save(update_fields=["status"])

        create_app_backup(backup)

        backup.status = Status.COMPLETED
        backup.error = "No errors. The backup was completed successfully."
        backup.completed_at = timezone.now()
        backup.save(update_fields=["status", "error", "completed_at"])

    except Exception as e:
        backup.status = Status.FAILED
        backup.error = str(e)
        backup.completed_at = timezone.now()

        backup.save(update_fields=["status", "error", "completed_at"])

@shared_task
def trigger_periodic_backup(periodec_backup_pk):
    try:
        periodic = PeriodicBackup.objects.select_related(
            "app"
        ).get(pk=periodec_backup_pk)

        queue_backup(
            app=periodic.app,
            source_path=periodic.source_path,
            periodic=periodic,
        )

    except PeriodicBackup.DoesNotExist:
        return

@shared_task
def fail_stale_backups():
    cutoff = timezone.now() - timedelta(hours=24)
    stale_backups = BackupJob.objects.filter(
        Q(status=Status.PENDING, created_at__lt=cutoff,) 
        | 
        Q(status=Status.RUNNING, created_at__lt=cutoff,))

    count = stale_backups.update(status=Status.FAILED, completed_at=timezone.now(),)

    if count:
        logger.warning("%s stale backup job(s) marked as faild.", count)