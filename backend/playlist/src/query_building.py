"""build Meilisearch search params for playlists"""

from playlist.src.constants import PlaylistTypesEnum


class QueryBuilder:
    """build Meilisearch search params for playlist listing"""

    def __init__(self, **kwargs):
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

    def _build_filters(self) -> list[str]:
        filters: list[str] = []

        channel = self.request_params.get("channel")
        if channel:
            filters.append(f"playlist_channel_id = {channel!r}")

        subscribed = self.request_params.get("subscribed")
        if subscribed is not None:
            val = "true" if subscribed else "false"
            filters.append(f"playlist_subscribed = {val}")

        playlist_type = self.request_params.get("type")
        if playlist_type:
            filters.append(self._parse_type_filter(playlist_type))

        return filters

    def _parse_type_filter(self, playlist_type: str) -> str:
        if not hasattr(PlaylistTypesEnum, playlist_type.upper()):
            raise ValueError(f"'{playlist_type}' not in PlaylistTypesEnum")

        type_parsed = getattr(PlaylistTypesEnum, playlist_type.upper()).value
        return f"playlist_type = {type_parsed!r}"

    def _build_sort(self) -> list[str]:
        return ["playlist_name:asc"]
