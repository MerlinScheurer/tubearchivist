"""send notifications using apprise"""

import apprise
from common.src.ta_redis import RedisArchivist
from task.src.task_config import TASK_CONFIG
from task.src.task_manager import TaskManager

REDIS_KEY = "notify"


class Notifications:
    """store notification URLs in Redis"""

    def __init__(self, task_name: str):
        self.task_name = task_name

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_all() -> dict:
        """return the full notify dict from Redis, or empty dict"""
        stored = RedisArchivist().get_message_dict(REDIS_KEY)
        return stored if isinstance(stored, dict) else {}

    @staticmethod
    def _save_all(data: dict) -> None:
        """persist the full notify dict to Redis"""
        RedisArchivist().set_message(REDIS_KEY, data, save=True)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def send(self, task_id: str, task_title: str) -> None:
        """send notifications"""
        apobj = apprise.Apprise()
        urls: list[str] = self.get_urls()
        if not urls:
            return

        title, body = self._build_message(task_id, task_title)

        if not body:
            return

        for url in urls:
            apobj.add(url)

        apobj.notify(body=body, title=title)

    def test(self, url) -> tuple[bool, str]:
        """send test notification"""
        try:
            apobj = apprise.Apprise()

            if not apobj.add(url):
                success = False
                message = f"Invalid notification URL format: {url}"
                return success, message

            title = f"[TA] {self.task_name} process ended with SUCCESS"
            body = "This is a test notification. Task completed successfully."

            result = apobj.notify(body=body, title=title)

            if result:
                success = True
                message = "Test notification sent successfully"
                return success, message

            success = False
            message = "Notification failed. Please check container logs for more information."
            return success, message

        except Exception as err:  # pylint: disable=broad-exception-caught
            success = False
            message = f"Notification error: {str(err)}"
            return success, message

    def _build_message(
        self, task_id: str, task_title: str
    ) -> tuple[str, str | None]:
        """build message to send notification"""
        task = TaskManager().get_task(task_id)
        status = task.get("status")
        title: str = f"[TA] {task_title} process ended with {status}"
        body: str | None = task.get("result")

        return title, body

    def get_urls(self) -> list[str]:
        """get stored URLs for this task"""
        data = self._get_all()
        return data.get(self.task_name, [])

    def add_url(self, url: str) -> None:
        """add URL to task notification list"""
        data = self._get_all()
        urls: list[str] = data.get(self.task_name, [])
        if url not in urls:
            urls.append(url)
            data[self.task_name] = urls
            self._save_all(data)

    def remove_url(self, url: str) -> tuple[dict, int]:
        """remove URL from task notification list"""
        data = self._get_all()
        urls: list[str] = data.get(self.task_name, [])
        if url in urls:
            urls.remove(url)
            if urls:
                data[self.task_name] = urls
            else:
                data.pop(self.task_name, None)
            self._save_all(data)

        if not self.get_urls():
            self.remove_task()

        return {}, 200

    def remove_task(self) -> tuple[dict, int]:
        """remove all notification URLs for this task"""
        data = self._get_all()
        data.pop(self.task_name, None)
        self._save_all(data)
        return {}, 200


def get_all_notifications() -> dict[str, list[str]]:
    """get all notifications stored"""
    stored = RedisArchivist().get_message_dict(REDIS_KEY)
    if not stored or not isinstance(stored, dict):
        return {}

    notifications: dict = {}
    for task_id, urls in stored.items():
        if task_id not in TASK_CONFIG:
            continue
        notifications[task_id] = {
            "urls": urls,
            "title": TASK_CONFIG[task_id]["title"],
        }

    return notifications
