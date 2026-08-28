import os
from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fintank_backend.settings")

app = Celery("fintank_backend")


@worker_process_init.connect
def reset_fsspec_state(**kwargs):
    """Give each forked prefork worker its own fsspec IO loop.

    fsspec keeps a module-global event loop and an instance cache, both created
    in the parent before the pool forks. Children inherit a loop bound to a
    thread that does not exist for them, and any cached S3FileSystem raises
    "This class is not fork-safe". Clearing both forces a per-process rebuild.
    """
    import fsspec.asyn
    import s3fs

    fsspec.asyn.reset_lock()
    s3fs.S3FileSystem.clear_instance_cache()

# Load config from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()
