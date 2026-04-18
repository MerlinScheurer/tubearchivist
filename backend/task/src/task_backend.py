"""
Functionality:
- Abstract Celery runtime operations behind a single interface
- Dispatch, control, and result management for background tasks
- Swap this module to replace Celery with another task backend
"""

from common.src.ta_redis import TaskRedis
from task.celery import app as celery_app


class TaskBackend:
    """single interface for all task backend operations"""

    # --- dispatch ---

    @staticmethod
    def dispatch(task_name: str, **kwargs) -> dict:
        """dispatch a task by name, returns task info dict"""
        result = celery_app.send_task(task_name, kwargs=kwargs)
        return {
            "task_id": result.id,
            "task_name": task_name,
        }

    # --- control ---

    @staticmethod
    def revoke(task_id: str) -> None:
        """kill a running task"""
        celery_app.control.revoke(task_id, terminate=True)

    @staticmethod
    def send_stop(task_id: str) -> None:
        """send cooperative stop signal to task"""
        TaskRedis().set_command(task_id, "STOP")

    # --- results ---

    @staticmethod
    def get_result(task_id: str) -> dict:
        """get single task result"""
        return TaskRedis().get_single(task_id)

    @staticmethod
    def get_all_results() -> list | bool:
        """return all task results"""
        handler = TaskRedis()
        all_keys = handler.get_all()
        if not all_keys:
            return False

        return [handler.get_single(i) for i in all_keys]

    @staticmethod
    def set_result(task_id: str, message: dict, expire=False):
        """set or update a task result"""
        TaskRedis().set_key(task_id, message, expire=expire)

    @staticmethod
    def is_stopped(task_id: str) -> bool:
        """check if task has received STOP command"""
        result = TaskRedis().get_single(task_id)
        return result.get("command") == "STOP"

    @classmethod
    def fail_pending(cls) -> None:
        """mark all pending tasks as failed (startup recovery)"""
        all_results = cls.get_all_results()
        if not all_results:
            return

        for result in all_results:
            if result.get("status") == "PENDING":
                result["status"] = "FAILED"
                cls.set_result(result["task_id"], result, expire=True)
