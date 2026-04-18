"""
Functionality:
- Unified abstraction for all Celery schedule management
- Validation, CRUD, defaults, timezone sync, config reads
"""

from datetime import datetime
from random import randint

from celery.schedules import crontab
from common.src.env_settings import EnvironmentSettings
from django.utils import dateformat
from django_celery_beat.models import CrontabSchedule, PeriodicTasks
from task.models import CustomPeriodicTask
from task.src.task_config import TASK_CONFIG


class TaskSchedule:
    """single entry point for all schedule operations"""

    SCHEDULES = {
        "update_subscribed": "0 8 *",
        "download_pending": "0 16 *",
        "check_reindex": "0 12 *",
        "thumbnail_check": "0 17 *",
        "run_backup": "0 18 0",
        "version_check": "0 11 *",
    }

    TASK_CONFIG_KEYS = {
        "check_reindex": ["days"],
        "run_backup": ["rotate"],
    }

    DEFAULT_SCHEDULES = {
        "check_reindex": {
            "schedule": "0 12 *",
            "config": {"days": 90},
        },
        "thumbnail_check": {
            "schedule": "0 17 *",
        },
        "version_check": {
            "schedule": "random",
        },
    }

    # --- validation ---

    @staticmethod
    def validate_cron(cron_expression: str) -> None:
        """validate a 3-field cron expression (minute hour day_of_week)"""
        if not cron_expression or cron_expression == "auto":
            return

        fields = cron_expression.split()
        if len(fields) != 3:
            raise ValueError("expected three cron schedule fields")

        minute, hour, day_of_week = fields

        if not minute.isdigit():
            raise ValueError("Invalid value for minutes. Must be an integer.")
        if not 0 <= int(minute) <= 59:
            raise ValueError("Invalid minutes. Must be between 0 and 59.")

        try:
            crontab(minute=minute, hour=hour, day_of_week=day_of_week)
        except ValueError as err:
            raise ValueError(f"invalid crontab: {err}") from err

    @classmethod
    def validate_config(cls, task_name: str, schedule_config: dict) -> None:
        """validate config keys for a given task"""
        if not schedule_config:
            return

        allowed = cls.TASK_CONFIG_KEYS.get(task_name)
        if not allowed:
            raise ValueError(f"task '{task_name}' doesn't take config")

        for key in schedule_config:
            if key not in allowed:
                raise ValueError(f"invalid config key for task '{task_name}'")

    # --- crontab helpers ---

    @staticmethod
    def _get_or_create_crontab(
        schedule: str,
    ) -> CrontabSchedule:
        """get or create a CrontabSchedule from '0 8 *' string"""
        kwargs = dict(
            zip(
                ["minute", "hour", "day_of_week"],
                schedule.split(),
            )
        )
        kwargs["timezone"] = EnvironmentSettings.TZ
        task_crontab, _ = CrontabSchedule.objects.get_or_create(**kwargs)
        return task_crontab

    # --- CRUD ---

    @classmethod
    def get_or_create(
        cls, task_name: str, schedule: str | None = None
    ) -> CustomPeriodicTask:
        """get existing task or create with optional schedule"""
        try:
            task = CustomPeriodicTask.objects.get(name=task_name)
        except CustomPeriodicTask.DoesNotExist:
            description = TASK_CONFIG[task_name].get("title")
            task = CustomPeriodicTask(
                name=task_name,
                task=task_name,
                description=description,
            )

        if schedule:
            task.crontab = cls._get_or_create_crontab(schedule)
            task.last_run_at = dateformat.make_aware(datetime.now())
            task.save()

        return task

    @classmethod
    def update(
        cls,
        task_name: str,
        cron_schedule: str,
        schedule_conf: dict | None = None,
    ) -> CustomPeriodicTask:
        """create or update a schedule, set config if provided"""
        if cron_schedule == "auto":
            cron_schedule = cls.SCHEDULES[task_name]

        task = cls.get_or_create(task_name, schedule=cron_schedule)

        if schedule_conf:
            cls.set_config(task_name, schedule_conf)

        return task

    @staticmethod
    def delete(task_name: str) -> None:
        """delete a schedule by task name, raises 404 if missing"""
        from django.shortcuts import get_object_or_404

        task = get_object_or_404(CustomPeriodicTask, name=task_name)
        task.delete()

    # --- config ---

    @staticmethod
    def set_config(task_name: str, config: dict) -> CustomPeriodicTask:
        """update task_config JSON on a task"""
        task = CustomPeriodicTask.objects.get(name=task_name)
        task.task_config.update(config)
        task.save()
        return task

    @staticmethod
    def get_config(task_name: str) -> dict:
        """read task_config for a task, returns {} if missing"""
        try:
            task = CustomPeriodicTask.objects.get(name=task_name)
        except CustomPeriodicTask.DoesNotExist:
            return {}

        return task.task_config

    # --- startup helpers ---

    @classmethod
    def create_defaults(cls) -> list[str]:
        """create default schedules for new installations.

        Returns list of created task names.
        """
        already_init = CustomPeriodicTask.objects.filter(
            name="version_check"
        ).exists()
        if already_init:
            return []

        created = []
        for task_name, spec in cls.DEFAULT_SCHEDULES.items():
            schedule = spec["schedule"]
            if schedule == "random":
                schedule = f"{randint(0, 59)} {randint(0, 23)} *"  # nosec

            task = cls.get_or_create(task_name, schedule=schedule)

            config = spec.get("config")
            if config:
                task.task_config.update(config)
                task.save()

            created.append(task_name)

        return created

    @staticmethod
    def sync_timezone() -> int:
        """ensure all CrontabSchedule objects use configured TZ.

        Returns count of updated schedules.
        """
        tz = EnvironmentSettings.TZ
        to_update = CrontabSchedule.objects.exclude(timezone=tz)
        if not to_update.exists():
            return 0

        updated = to_update.update(timezone=tz)
        PeriodicTasks.update_changed()
        return updated
