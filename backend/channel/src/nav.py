"""build channel nav"""

from common.src.es_connect import IndexPaginate, MeiliIndex


class ChannelNav:
    """get all nav items"""

    def __init__(self, channel_id):
        self.channel_id = channel_id

    def get_nav(self):
        """build nav items"""
        nav = {
            "has_pending": self._get_has_pending(),
            "has_ignored": self._get_has_ignored(),
            "has_playlists": self._get_has_playlists(),
        }
        nav.update(self._get_vid_types())
        return nav

    def _get_vid_types(self):
        """get available vid_types in given channel"""
        docs = IndexPaginate(
            "ta_video",
            {},
            filter_str=f"channel.channel_id = {self.channel_id!r}",
        ).get_results()

        type_nav = {
            "has_videos": False,
            "has_streams": False,
            "has_shorts": False,
        }
        for doc in docs:
            vid_type = doc.get("vid_type")
            if vid_type == "videos":
                type_nav["has_videos"] = True
            elif vid_type == "streams":
                type_nav["has_streams"] = True
            elif vid_type == "shorts":
                type_nav["has_shorts"] = True

            if all(type_nav.values()):
                break

        return type_nav

    def _get_has_pending(self):
        """check if has pending videos in download queue"""
        filter_str = f"status = 'pending' AND channel_id = {self.channel_id!r}"
        params = {"filter": filter_str, "limit": 1}
        response = MeiliIndex("ta_download").search("", params)
        return bool(response.get("hits"))

    def _get_has_ignored(self):
        """Check if there are ignored videos in the download queue"""
        filter_str = f"status = 'ignore' AND channel_id = {self.channel_id!r}"
        params = {"filter": filter_str, "limit": 1}
        response = MeiliIndex("ta_download").search("", params)
        return bool(response.get("hits"))

    def _get_has_playlists(self):
        """check if channel has playlists"""
        filter_str = f"playlist_channel_id = {self.channel_id!r}"
        params = {"filter": filter_str, "limit": 1}
        response = MeiliIndex("ta_playlist").search("", params)
        return bool(response.get("hits"))
