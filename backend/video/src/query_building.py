"""build Meilisearch search params for video fetching"""

from common.src.ta_redis import RedisArchivist
from playlist.src.index import YoutubePlaylist
from video.src.constants import OrderEnum, SortEnum, VideoTypeEnum


class QueryBuilder:
    """build Meilisearch search params for video listing"""

    WATCH_OPTIONS = ["watched", "unwatched", "continue"]

    def __init__(self, user_id: int, **kwargs):
        self.user_id = user_id
        self.request_params = kwargs

    def build_data(self) -> dict:
        """build Meilisearch params dict"""
        params: dict = {}

        filters = self._build_filters()
        if filters:
            params["filter"] = " AND ".join(filters)

        sort = self._build_sort()
        if sort:
            params["sort"] = sort

        return params

    # ------------------------------------------------------------------
    # filters
    # ------------------------------------------------------------------

    def _build_filters(self) -> list[str]:
        filters: list[str] = []

        channel = self.request_params.get("channel")
        if channel:
            filters.append(f"channel.channel_id = {channel!r}")

        playlist = self.request_params.get("playlist")
        if playlist:
            filters.append(f"playlist = {playlist!r}")

        watch = self.request_params.get("watch")
        if watch is not None:
            watch_filter = self._parse_watch_filter(watch)
            if watch_filter:
                filters.append(watch_filter)

        video_type = self.request_params.get("type")
        if video_type:
            type_filter = self._parse_type_filter(video_type)
            if type_filter:
                filters.append(type_filter)

        return filters

    def _parse_watch_filter(self, watch: str) -> str | None:
        if watch not in self.WATCH_OPTIONS:
            raise ValueError(f"'{watch}' not in {self.WATCH_OPTIONS}")

        if watch == "continue":
            return self._build_continue_filter()

        val = "true" if watch == "watched" else "false"
        return f"player.watched = {val}"

    def _build_continue_filter(self) -> str | None:
        results = RedisArchivist().list_items(f"{self.user_id}:progress:")
        if not results:
            return None

        ids = [
            f"youtube_id = {i['youtube_id']!r}"
            for i in results
            if not i.get("watched") and i.get("youtube_id")
        ]
        if not ids:
            return None

        # Meilisearch OR filter: wrap in parentheses
        return "(" + " OR ".join(ids) + ")"

    def _parse_type_filter(self, video_type: str) -> str:
        if not hasattr(VideoTypeEnum, video_type.upper()):
            raise ValueError(f"'{video_type}' not in VideoTypeEnum")

        vid_type = getattr(VideoTypeEnum, video_type.upper()).value
        return f"vid_type = {vid_type!r}"

    # ------------------------------------------------------------------
    # sort
    # ------------------------------------------------------------------

    def _build_sort(self) -> list[str] | None:
        playlist = self.request_params.get("playlist")
        if playlist:
            return None  # handled via get_playlist_sort_key

        sort = self.request_params.get("sort")
        if not sort:
            return None

        sort_names = SortEnum.names()
        if sort not in sort_names:
            raise ValueError(f"'{sort}' not a valid sort field")

        sort_field = SortEnum[sort.upper()].value
        order = self.request_params.get("order", "desc")
        if order not in ("asc", "desc"):
            raise ValueError(f"'{order}' not in OrderEnum")

        return [f"{sort_field}:{order}"]

    def get_playlist_sort_key(self, playlist_id: str):
        """return a sort-key function for post-retrieval playlist ordering"""
        playlist = YoutubePlaylist(playlist_id)
        playlist.get_from_es()
        if not playlist.json_data:
            raise ValueError(f"playlist {playlist_id} not found")

        sort_score = {
            i["youtube_id"]: i["idx"]
            for i in playlist.json_data["playlist_entries"]
            if i["downloaded"]
        }
        return lambda doc: sort_score.get(doc.get("youtube_id"), 100000)
