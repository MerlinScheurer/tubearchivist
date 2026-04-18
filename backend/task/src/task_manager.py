"""
functionality:
- interact with in redis stored task results
- handle threads and locks
"""

from task.src.task_backend import TaskBackend


class TaskManager:
    """manage tasks"""

    def get_all_results(self):
        """return all task results"""
        return TaskBackend.get_all_results()

    def get_tasks_by_name(self, task_name):
        """get all tasks by name"""
        all_results = self.get_all_results()
        if not all_results:
            return False

        return [i for i in all_results if i.get("name") == task_name]

    def get_task(self, task_id):
        """get single task"""
        return TaskBackend.get_result(task_id)

    def is_pending(self, task):
        """check if task_name is pending, pass task object"""
        tasks = self.get_tasks_by_name(task.name)
        if not tasks:
            return False

        return bool([i for i in tasks if i.get("status") == "PENDING"])

    def is_stopped(self, task_id):
        """check if task_id has received STOP command"""
        return TaskBackend.is_stopped(task_id)

    def get_pending(self, task_name):
        """get all pending tasks of task_name"""
        tasks = self.get_tasks_by_name(task_name)
        if not tasks:
            return False

        return [i for i in tasks if i.get("status") == "PENDING"]

    def init(self, task):
        """pass task object from bind task to set initial message"""
        message = {
            "status": "PENDING",
            "result": None,
            "traceback": None,
            "date_done": False,
            "name": task.name,
            "task_id": task.request.id,
        }
        TaskBackend.set_result(task.request.id, message)

    def fail_pending(self):
        """
        mark all pending as failed,
        run at startup to recover from hard reset
        """
        TaskBackend.fail_pending()


class TaskCommand:
    """run commands on task"""

    def start(self, task_name, kwargs: dict | None = None):
        """start task by task_name"""
        return TaskBackend.dispatch(task_name, **(kwargs or {}))

    def stop(self, task_id):
        """
        send stop signal to task_id,
        needs to be implemented in task to take effect
        """
        print(f"[task][{task_id}]: received STOP signal.")
        TaskBackend.send_stop(task_id)

    def kill(self, task_id):
        """send kill signal to task_id"""
        print(f"[task][{task_id}]: received KILL signal.")
        TaskBackend.revoke(task_id)
