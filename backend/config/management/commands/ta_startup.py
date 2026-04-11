"""
Functionality:
- Application startup
- Apply migrations
"""

import os
from datetime import datetime
from random import randint
from time import sleep

from appsettings.src.config import AppConfig, ReleaseVersion
from appsettings.src.index_setup import ElasticIndexWrap
from channel.src.index import YoutubeChannel
from common.src.env_settings import EnvironmentSettings
from common.src.es_connect import IndexPaginate, MeiliIndex
from common.src.helper import clear_dl_cache, get_channels
from common.src.ta_redis import RedisArchivist
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import dateformat
from django_celery_beat.models import CrontabSchedule, PeriodicTasks
from task.models import CustomPeriodicTask
from task.src.config_schedule import ScheduleBuilder
from task.src.task_manager import TaskManager
from task.tasks import version_check
from video.src.constants import VideoTypeEnum
from video.src.index import YoutubeVideo

TOPIC = """

#######################
#  Application Start  #
#######################

"""


class Command(BaseCommand):
    """command framework"""

    def handle(self, *args, **options):
        """run all commands"""
        self.stdout.write(TOPIC)
        self._make_folders()
        self._clear_redis_keys()
        self._clear_tasks()
        self._clear_dl_cache()
        self._version_check()
        self._index_setup()
        self._create_default_schedules()
        self._update_schedule_tz()
        self._init_app_config()
        self._set_ta_startup_time()

        if self.skip_migrations:
            return

        self._mig_add_default_playlist_sort()
        self._mig_set_channel_tabs()
        self._mig_set_video_channel_tabs()
        self._mig_fix_playlist_description()
        self._mig_fix_missing_stats()
        self._mig_fix_channel_art_types()
        self._mig_fix_channel_description()
        self._mig_fix_video_description()

    @property
    def skip_migrations(self) -> bool:
        """
        check if migrations should be skipped.
        Experimental, might get replaced in the future.
        """
        current_version = settings.TA_VERSION.rstrip("-unstable").upper()
        env_var = f"TA_MIG_SKIP_{current_version}"
        skipping = bool(os.environ.get(env_var))

        self.stdout.write("[MIGRATION] check, experimental")
        if skipping:
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {env_var} is set, skipping migration check"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "    Running migrations. "
                    + "If migrations have run for this release, "
                    + f"you can set {env_var} to skip the check"
                )
            )

        return skipping

    def _make_folders(self):
        """make expected cache folders"""
        self.stdout.write("[1] create expected cache folders")
        folders = [
            "backup",
            "channels",
            "download",
            "import",
            "playlists",
            "videos",
            "ytdlp",
        ]
        cache_dir = EnvironmentSettings.CACHE_DIR
        for folder in folders:
            folder_path = os.path.join(cache_dir, folder)
            os.makedirs(folder_path, exist_ok=True)

        self.stdout.write(self.style.SUCCESS("    ✓ expected folders created"))

    def _clear_redis_keys(self):
        """make sure there are no leftover locks or keys set in redis"""
        self.stdout.write("[2] clear leftover keys in redis")
        all_keys = [
            "dl_queue_id",
            "dl_queue",
            "downloading",
            "manual_import",
            "reindex",
            "rescan",
            "run_backup",
            "startup_check",
            "reindex:ta_video",
            "reindex:ta_channel",
            "reindex:ta_playlist",
        ]

        redis_con = RedisArchivist()
        has_changed = False
        for key in all_keys:
            if redis_con.del_message(key):
                self.stdout.write(
                    self.style.SUCCESS(f"    ✓ cleared key {key}")
                )
                has_changed = True

        if not has_changed:
            self.stdout.write(self.style.SUCCESS("    no keys found"))

    def _clear_tasks(self):
        """clear tasks and messages"""
        self.stdout.write("[3] clear task leftovers")
        TaskManager().fail_pending()
        redis_con = RedisArchivist()
        to_delete = redis_con.list_keys("message:")
        if to_delete:
            for key in to_delete:
                redis_con.del_message(key)

            self.stdout.write(
                self.style.SUCCESS(f"    ✓ cleared {len(to_delete)} messages")
            )

    def _clear_dl_cache(self):
        """clear leftover files from dl cache"""
        self.stdout.write("[4] clear leftover files from dl cache")
        leftover_files = clear_dl_cache(EnvironmentSettings.CACHE_DIR)
        if leftover_files:
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ cleared {leftover_files} files")
            )
        else:
            self.stdout.write(self.style.SUCCESS("    no files found"))

    def _version_check(self):
        """remove new release key if updated now"""
        self.stdout.write("[5] check for first run after update")
        new_version = ReleaseVersion().is_updated()
        if new_version:
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ update to {new_version} completed")
            )
        else:
            self.stdout.write(self.style.SUCCESS("    no new update found"))

        version_task = CustomPeriodicTask.objects.filter(name="version_check")
        if not version_task.exists():
            return

        if not version_task.first().last_run_at:
            self.style.SUCCESS("    ✓ send initial version check task")
            version_check.delay()

    def _index_setup(self):
        """migration: validate index mappings"""
        self.stdout.write("[6] validate index mappings")
        ElasticIndexWrap().setup()

    def _create_default_schedules(self) -> None:
        """create default schedules for new installations"""
        self.stdout.write("[7] create initial schedules")
        init_has_run = CustomPeriodicTask.objects.filter(
            name="version_check"
        ).exists()

        if init_has_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "    schedule init already done, skipping..."
                )
            )
            return

        builder = ScheduleBuilder()
        check_reindex = builder.get_set_task(
            "check_reindex", schedule=builder.SCHEDULES["check_reindex"]
        )
        check_reindex.task_config.update({"days": 90})
        check_reindex.last_run_at = dateformat.make_aware(datetime.now())
        check_reindex.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"    ✓ created new default schedule: {check_reindex}"
            )
        )

        thumbnail_check = builder.get_set_task(
            "thumbnail_check", schedule=builder.SCHEDULES["thumbnail_check"]
        )
        thumbnail_check.last_run_at = dateformat.make_aware(datetime.now())
        thumbnail_check.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"    ✓ created new default schedule: {thumbnail_check}"
            )
        )
        daily_random = f"{randint(0, 59)} {randint(0, 23)} *"
        version_check_task = builder.get_set_task(
            "version_check", schedule=daily_random
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"    ✓ created new default schedule: {version_check_task}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS("    ✓ all default schedules created")
        )

    def _update_schedule_tz(self) -> None:
        """update timezone for Schedule instances"""
        self.stdout.write("[8] validate schedules TZ")
        tz = EnvironmentSettings.TZ
        to_update = CrontabSchedule.objects.exclude(timezone=tz)

        if not to_update.exists():
            self.stdout.write(
                self.style.SUCCESS("    all schedules have correct TZ")
            )
            return

        updated = to_update.update(timezone=tz)
        self.stdout.write(
            self.style.SUCCESS(f"    ✓ updated {updated} schedules to {tz}.")
        )
        PeriodicTasks.update_changed()

    def _init_app_config(self) -> None:
        """init default app config to Redis"""
        self.stdout.write("[9] Check AppConfig")
        config = AppConfig()
        if config.config:
            self.stdout.write(
                self.style.SUCCESS("    skip completed appsettings init")
            )
            updated_defaults = config.add_new_defaults()
            for new_default in updated_defaults:
                self.stdout.write(
                    self.style.SUCCESS(f"    added new default: {new_default}")
                )

            cleared = config.clear_old_keys()
            for removed_key in cleared:
                self.stdout.write(
                    self.style.SUCCESS(f"    removed old key: {removed_key}")
                )

            return

        config.sync_defaults()
        self.stdout.write(
            self.style.SUCCESS("    ✓ Created default appsettings.")
        )

    def _set_ta_startup_time(self) -> None:
        """set startup time to trigger frontend refresh, threadsafe"""
        self.stdout.write("[10] Set startup timestamp")
        message = str(int(datetime.now().timestamp() // 10 * 10))
        RedisArchivist().set_message(
            "STARTTIMESTAMP", message=message, save=True
        )
        self.stdout.write(
            self.style.SUCCESS(f"    ✓ set timestamp to {message}.")
        )

    # ------------------------------------------------------------------
    # Migrations: all Painless _update_by_query replaced with
    #   fetch-in-Python → update fields → re-index
    # ------------------------------------------------------------------

    def _mig_add_default_playlist_sort(self) -> None:
        """migrate from 0.5.4 to 0.5.5 set default playlist sortorder"""
        desc = "set default playlist sort order"
        self.stdout.write(f"[MIGRATION] run {desc}")
        docs = IndexPaginate("ta_playlist", {}).get_results()
        updated = [
            {**d, "playlist_sort_order": "top"}
            for d in docs
            if not d.get("playlist_sort_order")
        ]
        if updated:
            MeiliIndex("ta_playlist").add_documents(updated)
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {len(updated)} playlists")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_set_channel_tabs(self) -> None:
        """migrate from 0.5.4 to 0.5.5 set initial channel tabs"""
        desc = "set default channel_tabs in channel index"
        self.stdout.write(f"[MIGRATION] run {desc}")
        tabs = VideoTypeEnum.values_known()
        docs = IndexPaginate("ta_channel", {}).get_results()
        updated = [
            {**d, "channel_tabs": tabs}
            for d in docs
            if not d.get("channel_tabs")
        ]
        if updated:
            MeiliIndex("ta_channel").add_documents(updated)
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {len(updated)} channels")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_set_video_channel_tabs(self) -> None:
        """migrate from 0.5.4 to 0.5.5 set initial video channel tabs"""
        desc = "set default channel_tabs for videos"
        self.stdout.write(f"[MIGRATION] run {desc}")
        tabs = VideoTypeEnum.values_known()
        docs = IndexPaginate("ta_video", {}).get_results()
        updated = []
        for d in docs:
            channel = d.get("channel") or {}
            if not channel.get("channel_tabs"):
                channel["channel_tabs"] = tabs
                d["channel"] = channel
                updated.append(d)
        if updated:
            MeiliIndex("ta_video").add_documents(updated)
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {len(updated)} videos")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_fix_playlist_description(self) -> None:
        """migrate from 0.5.8 to 0.5.9 fix playlist desc null data type"""
        desc = "fix playlist description data type"
        self.stdout.write(f"[MIGRATION] run {desc}")
        docs = IndexPaginate("ta_playlist", {}).get_results()
        updated = []
        for d in docs:
            if d.get("playlist_description") is False:
                d.pop("playlist_description", None)
                updated.append(d)
        if updated:
            MeiliIndex("ta_playlist").add_documents(updated)
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {len(updated)} playlists")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_fix_missing_stats(self) -> None:
        """migrate from 0.5.8 to 0.5.9, fix missing stats values"""
        desc = "fix missing stats fields"
        self.stdout.write(f"[MIGRATION] run {desc}")
        fields = [
            "like_count",
            "average_rating",
            "view_count",
            "dislike_count",
        ]
        docs = IndexPaginate("ta_video", {}).get_results()
        updated = []
        for d in docs:
            stats = d.get("stats") or {}
            changed = False
            for field in fields:
                if field not in stats:
                    stats[field] = 0
                    changed = True
            if changed:
                d["stats"] = stats
                updated.append(d)
        if updated:
            MeiliIndex("ta_video").add_documents(updated)
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {len(updated)} videos")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_fix_channel_art_types(self) -> None:
        """migrate from 0.5.8 to 0.5.9, fix channel artwork types"""
        desc = "fix channel artwork types"
        self.stdout.write(f"[MIGRATION] run {desc}")
        art_fields = [
            "channel_banner_url",
            "channel_thumb_url",
            "channel_tvart_url",
        ]

        # Fix channel index
        channel_docs = IndexPaginate("ta_channel", {}).get_results()
        updated_channels = []
        for d in channel_docs:
            changed = False
            for field in art_fields:
                if d.get(field) is False:
                    d.pop(field, None)
                    changed = True
            if changed:
                updated_channels.append(d)
        if updated_channels:
            MeiliIndex("ta_channel").add_documents(updated_channels)

        # Fix video index (channel sub-object)
        video_docs = IndexPaginate("ta_video", {}).get_results()
        updated_videos = []
        for d in video_docs:
            channel = d.get("channel") or {}
            changed = False
            for field in art_fields:
                if channel.get(field) is False:
                    channel.pop(field, None)
                    changed = True
            if changed:
                d["channel"] = channel
                updated_videos.append(d)
        if updated_videos:
            MeiliIndex("ta_video").add_documents(updated_videos)

        total = len(updated_channels) + len(updated_videos)
        if total:
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ updated {total} documents")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("    no items needed updating")
            )

    def _mig_fix_channel_description(self) -> None:
        """migrate from 0.5.8 to 0.5.9, fix channel desc null value"""
        desc = "fix channel description null value"
        self.stdout.write(f"[MIGRATION] run {desc}")
        channels = get_channels(
            subscribed_only=False, source=["channel_description", "channel_id"]
        )
        counter = 0
        for channel_response in channels:
            if not channel_response.get("channel_description") == "":
                continue

            channel = YoutubeChannel(youtube_id=channel_response["channel_id"])
            channel.get_from_es()
            channel.json_data.pop("channel_description")
            channel.upload_to_es()
            channel.sync_to_videos()
            counter += 1

        if counter:
            suc_msg = f"    ✓ updated {counter} channels with videos"
            self.stdout.write(self.style.SUCCESS(suc_msg))
        else:
            noop_msg = "    no items needed updating"
            self.stdout.write(self.style.SUCCESS(noop_msg))

    def _mig_fix_video_description(self) -> None:
        """migrate from 0.5.8 to 0.5.9, fix video desc null value"""
        desc = "fix video description null value"
        self.stdout.write(f"[MIGRATION] run {desc}")

        docs = IndexPaginate("ta_video", {}).get_results()

        counter = 0
        updated = []
        for video_response in docs:
            if not video_response.get("description") == "":
                continue

            video_response.pop("description")
            updated.append(video_response)
            counter += 1

        if updated:
            MeiliIndex("ta_video").add_documents(updated)

        if counter:
            suc_msg = f"    ✓ updated {counter} videos"
            self.stdout.write(self.style.SUCCESS(suc_msg))
        else:
            noop_msg = "    no items needed updating"
            self.stdout.write(self.style.SUCCESS(noop_msg))
