"""aggregations — computed in Python from Meilisearch browse results"""

from collections import defaultdict
from datetime import datetime, timedelta

from common.src.env_settings import EnvironmentSettings
from common.src.es_connect import IndexPaginate, MeiliIndex
from common.src.helper import get_duration_str


class Video:
    """get video stats"""

    name = "video_stats"

    def process(self):
        """compute video aggregations"""
        docs = IndexPaginate("ta_video", {}).get_results()
        if not docs:
            return None

        total_size = 0
        total_duration = 0
        total_count = len(docs)
        by_type: dict = defaultdict(
            lambda: {"doc_count": 0, "media_size": 0, "duration": 0}
        )
        by_active: dict = defaultdict(
            lambda: {"doc_count": 0, "media_size": 0, "duration": 0}
        )

        for doc in docs:
            size = doc.get("media_size") or 0
            duration = (doc.get("player") or {}).get("duration") or 0
            vid_type = doc.get("vid_type") or "unknown"
            active = str(doc.get("active", False)).lower()

            total_size += size
            total_duration += duration

            by_type[vid_type]["doc_count"] += 1
            by_type[vid_type]["media_size"] += size
            by_type[vid_type]["duration"] += duration

            by_active[active]["doc_count"] += 1
            by_active[active]["media_size"] += size
            by_active[active]["duration"] += duration

        response = {
            "doc_count": total_count,
            "media_size": total_size,
            "duration": total_duration,
            "duration_str": get_duration_str(total_duration),
        }

        for vtype, data in by_type.items():
            dur = int(data["duration"])
            response[f"type_{vtype}"] = {
                "doc_count": data["doc_count"],
                "media_size": data["media_size"],
                "duration": dur,
                "duration_str": get_duration_str(dur),
            }

        for active_key, data in by_active.items():
            dur = int(data["duration"])
            response[f"active_{active_key}"] = {
                "doc_count": data["doc_count"],
                "media_size": data["media_size"],
                "duration": dur,
                "duration_str": get_duration_str(dur),
            }

        return response


class Channel:
    """get channel stats"""

    name = "channel_stats"

    def process(self):
        """compute channel aggregations"""
        docs = IndexPaginate("ta_channel", {}).get_results()
        if not docs:
            return None

        total_count = len(docs)
        by_active: dict = defaultdict(int)
        by_subscribed: dict = defaultdict(int)

        for doc in docs:
            active_key = str(doc.get("channel_active", False)).lower()
            subscribed_key = str(doc.get("channel_subscribed", False)).lower()
            by_active[active_key] += 1
            by_subscribed[subscribed_key] += 1

        response = {"doc_count": total_count}
        for key, count in by_active.items():
            response[f"active_{key}"] = count
        for key, count in by_subscribed.items():
            response[f"subscribed_{key}"] = count

        return response


class Playlist:
    """get playlist stats"""

    name = "playlist_stats"

    def process(self):
        """compute playlist aggregations"""
        docs = IndexPaginate("ta_playlist", {}).get_results()
        if not docs:
            return None

        total_count = len(docs)
        by_active: dict = defaultdict(int)
        by_subscribed: dict = defaultdict(int)

        for doc in docs:
            active_key = str(doc.get("playlist_active", False)).lower()
            subscribed_key = str(doc.get("playlist_subscribed", False)).lower()
            by_active[active_key] += 1
            by_subscribed[subscribed_key] += 1

        response = {"doc_count": total_count}
        for key, count in by_active.items():
            response[f"active_{key}"] = count
        for key, count in by_subscribed.items():
            response[f"subscribed_{key}"] = count

        return response


class Download:
    """get downloads queue stats"""

    name = "download_queue_stats"

    def process(self):
        """compute download queue aggregations"""
        docs = IndexPaginate("ta_download", {}).get_results()
        if not docs:
            return None

        by_status: dict = defaultdict(int)
        pending_by_type: dict = defaultdict(int)

        for doc in docs:
            status = doc.get("status") or "unknown"
            by_status[status] += 1
            if status == "pending":
                vid_type = doc.get("vid_type") or "unknown"
                pending_by_type[vid_type] += 1

        response = dict(by_status)
        for vtype, count in pending_by_type.items():
            response[f"pending_{vtype}"] = count

        return response


class WatchProgress:
    """get watch progress"""

    name = "watch_progress"

    def process(self):
        """compute watch progress aggregations"""
        docs = IndexPaginate("ta_video", {}).get_results()
        if not docs:
            return None

        total_duration = 0
        total_items = len(docs)
        watched_duration = 0
        watched_items = 0
        unwatched_duration = 0
        unwatched_items = 0

        for doc in docs:
            duration = (doc.get("player") or {}).get("duration") or 0
            watched = (doc.get("player") or {}).get("watched", False)
            total_duration += duration
            if watched:
                watched_duration += duration
                watched_items += 1
            else:
                unwatched_duration += duration
                unwatched_items += 1

        response = {
            "total": {
                "duration": total_duration,
                "duration_str": get_duration_str(total_duration),
                "items": total_items,
            },
            "watched": {
                "duration": watched_duration,
                "duration_str": get_duration_str(watched_duration),
                "progress": (
                    watched_duration / total_duration if total_duration else 0
                ),
                "items": watched_items,
            },
            "unwatched": {
                "duration": unwatched_duration,
                "duration_str": get_duration_str(unwatched_duration),
                "progress": (
                    unwatched_duration / total_duration
                    if total_duration
                    else 0
                ),
                "items": unwatched_items,
            },
        }

        return response


class DownloadHist:
    """get downloads histogram last 7 days"""

    name = "videos_last_week"

    def process(self):
        """compute last-7-days download histogram"""
        tz_name = EnvironmentSettings.TZ
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None

        now = datetime.now(tz) if tz else datetime.now()
        cutoff = int((now - timedelta(days=7)).timestamp())

        filter_str = f"date_downloaded >= {cutoff}"
        docs = IndexPaginate(
            "ta_video", {}, filter_str=filter_str
        ).get_results()

        by_day: dict = defaultdict(lambda: {"count": 0, "media_size": 0})
        for doc in docs:
            ts = doc.get("date_downloaded")
            if not ts:
                continue
            if tz:
                day = datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")
            else:
                day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

            by_day[day]["count"] += 1
            by_day[day]["media_size"] += doc.get("media_size") or 0

        # Return sorted descending, last 7 days only
        response = [
            {
                "date": day,
                "count": data["count"],
                "media_size": data["media_size"],
            }
            for day, data in sorted(by_day.items(), reverse=True)
        ]

        return response


class BiggestChannel:
    """get channel aggregations by video count, duration, or media size"""

    name = "channel_stats"
    order_choices = ["doc_count", "duration", "media_size"]

    def __init__(self, order):
        if order not in self.order_choices:
            order = "doc_count"
        self.order = order

    def process(self):
        """compute per-channel aggregations"""
        docs = IndexPaginate("ta_video", {}).get_results()
        if not docs:
            return None

        channels: dict = defaultdict(
            lambda: {
                "name": "",
                "doc_count": 0,
                "duration": 0,
                "media_size": 0,
            }
        )

        for doc in docs:
            channel = doc.get("channel") or {}
            channel_id = channel.get("channel_id") or "unknown"
            channel_name = channel.get("channel_name") or channel_id
            duration = (doc.get("player") or {}).get("duration") or 0
            size = doc.get("media_size") or 0

            channels[channel_id]["name"] = channel_name
            channels[channel_id]["doc_count"] += 1
            channels[channel_id]["duration"] += duration
            channels[channel_id]["media_size"] += size

        response = [
            {
                "id": cid,
                "name": data["name"].title(),
                "doc_count": data["doc_count"],
                "duration": data["duration"],
                "duration_str": get_duration_str(int(data["duration"])),
                "media_size": data["media_size"],
            }
            for cid, data in channels.items()
        ]

        response.sort(key=lambda x: x[self.order], reverse=True)

        return response
