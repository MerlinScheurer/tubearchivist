"""
functionality:
- setup Meilisearch indexes at first start
- verify and update index settings if needed
- backup and restore metadata
"""

import meilisearch
from appsettings.src.backup import ElasticBackup
from appsettings.src.config import AppConfig
from common.src.es_connect import MeiliIndex, get_meili_client
from common.src.helper import get_mapping


class MeiliIndexSetup:
    """manage a single Meilisearch index"""

    def __init__(self, index_name: str, primary_key: str, settings: dict):
        self.index_name = index_name
        self.primary_key = primary_key
        self.expected_settings = settings
        self._client = get_meili_client()

    def index_exists(self) -> bool:
        """check whether the index already exists in Meilisearch"""
        try:
            self._client.get_index(self.index_name)
            return True
        except meilisearch.errors.MeilisearchApiError as exc:
            if exc.code == "index_not_found":
                return False
            raise

    def create(self) -> None:
        """create index with the configured primary key"""
        print(f"[{self.index_name}] creating new index")
        task = self._client.create_index(
            self.index_name, {"primaryKey": self.primary_key}
        )
        self._client.wait_for_task(task.task_uid)
        self.apply_settings()

    def apply_settings(self) -> None:
        """apply searchable/filterable/sortable attribute settings"""
        print(f"[{self.index_name}] applying settings")
        index = MeiliIndex(self.index_name)
        task_info = index.update_settings(self.expected_settings)
        # task_info may be a task object or dict depending on SDK version
        task_uid = (
            task_info.task_uid
            if hasattr(task_info, "task_uid")
            else task_info.get("uid") or task_info.get("taskUid")
        )
        if task_uid:
            self._client.wait_for_task(task_uid)

    def setup(self) -> None:
        """create index if it does not exist, otherwise verify settings"""
        if not self.index_exists():
            self.create()
            return

        print(f"[{self.index_name}] index already exists, updating settings")
        self.apply_settings()

    def delete(self) -> None:
        """delete the index"""
        print(f"[{self.index_name}] deleting index")
        task = self._client.delete_index(self.index_name)
        self._client.wait_for_task(task.task_uid)


class MeiliIndexWrap:
    """manage all Meilisearch indexes"""

    def __init__(self):
        self.index_config: list = get_mapping()
        self.backup_run = False

    def setup(self) -> None:
        """create/verify all indexes — run at startup"""
        for entry in self.index_config:
            handler = self._make_handler(entry)
            handler.setup()

    def reset(self) -> None:
        """delete and recreate all indexes from scratch"""
        self.delete_all()
        self.create_all()

    def delete_all(self) -> None:
        """delete all indexes"""
        for entry in self.index_config:
            handler = self._make_handler(entry)
            if handler.index_exists():
                handler.delete()

    def create_all(self) -> None:
        """create all blank indexes"""
        print("creating all Meilisearch indexes from config")
        for entry in self.index_config:
            handler = self._make_handler(entry)
            handler.create()

    @staticmethod
    def _make_handler(entry: dict) -> MeiliIndexSetup:
        return MeiliIndexSetup(
            index_name=entry["index_name"],
            primary_key=entry["primary_key"],
            settings=entry["settings"],
        )

    def _check_backup(self) -> None:
        """create JSON backup before a destructive operation"""
        if self.backup_run:
            return

        try:
            config = AppConfig().config
        except ValueError:
            print("AppConfig not found, creating defaults...")
            handler = AppConfig.__new__(AppConfig)
            handler.sync_defaults()
            config = AppConfig.CONFIG_DEFAULTS

        # snapshot support removed; always fall back to JSON backup
        ElasticBackup(reason="update").backup_all_indexes()
        self.backup_run = True


# Keep old name importable so that any remaining callers get a clear error
# rather than an AttributeError.
ElasticIndexWrap = MeiliIndexWrap
ElasticIndex = MeiliIndexSetup
