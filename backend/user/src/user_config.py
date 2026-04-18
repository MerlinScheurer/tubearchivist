"""
Functionality:
- read and write user config backed by Redis
- encapsulate persistence of user properties
"""

from typing import TypedDict

from common.src.ta_redis import RedisArchivist


class UserConfigType(TypedDict, total=False):
    """describes the user configuration"""

    stylesheet: str
    page_size: int
    sort_by: str
    sort_order: str
    view_style_home: str
    view_style_channel: str
    view_style_downloads: str
    view_style_playlist: str
    vid_type_filter: str | None
    grid_items: int
    hide_watched: bool | None
    hide_watched_channel: bool | None
    hide_watched_playlist: bool | None
    file_size_unit: str
    show_ignored_only: bool
    show_subed_only: bool | None
    show_subed_only_playlists: bool | None
    show_help_text: bool


class UserConfig:
    """
    Handle settings for an individual user.
    Stored in Redis under key  user_config:<user_id>  (persisted to disk).
    """

    _DEFAULT_USER_SETTINGS = UserConfigType(
        stylesheet="dark.css",
        page_size=25,
        sort_by="published",
        sort_order="desc",
        view_style_home="grid",
        view_style_channel="list",
        view_style_downloads="list",
        view_style_playlist="grid",
        vid_type_filter=None,
        grid_items=3,
        hide_watched=False,
        hide_watched_channel=None,
        hide_watched_playlist=None,
        file_size_unit="binary",
        show_ignored_only=False,
        show_subed_only=None,
        show_subed_only_playlists=None,
        show_help_text=True,
    )

    def __init__(self, user_id: str):
        self._user_id: str = user_id
        self._config: UserConfigType = self.get_config()

    @property
    def _redis_key(self) -> str:
        return f"user_config:{self._user_id}"

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> dict | None:
        return RedisArchivist().get_message_dict(self._redis_key)

    def _write(self, config: dict) -> None:
        RedisArchivist().set_message(self._redis_key, config, save=True)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get_value(self, key: str):
        """Get the given key from the user's configuration.
        Raises KeyError if the key is not a permitted value."""
        if key not in self._DEFAULT_USER_SETTINGS:
            raise KeyError(f"Unable to read config for unknown key '{key}'")
        return self._config.get(key)

    def set_value(self, key: str, value: str | bool | int) -> None:
        """Set or replace a single configuration value for the user."""
        if key not in self._DEFAULT_USER_SETTINGS:
            raise KeyError(f"Unable to set config for unknown key '{key}'")
        config = dict(self._config)
        config[key] = value
        self._write(config)
        self._config = config  # type: ignore
        print(f"User {self._user_id} value '{key}' change: to {value}")

    def get_config(self) -> UserConfigType:
        """Return config from Redis, writing defaults on first access."""
        if not self._user_id:
            raise ValueError("no user_id passed")

        stored = self._read()
        if not stored:
            self.sync_defaults()
            return self._DEFAULT_USER_SETTINGS

        return self.sync_new_defaults(stored)  # type: ignore

    def update_config(self, to_update: dict) -> None:
        """Merge partial update dict into stored config."""
        config = dict(self._config)
        config.update(to_update)
        self._write(config)
        self._config = config  # type: ignore
        for key, value in to_update.items():
            print(f"User {self._user_id} value '{key}' change: to {value}")

    def sync_defaults(self) -> None:
        """Write initial defaults for a new user."""
        self._write(dict(self._DEFAULT_USER_SETTINGS))
        print(f"set default config for user {self._user_id}")

    def sync_new_defaults(self, config: dict) -> UserConfigType:
        """Add any keys present in defaults but missing from stored config."""
        changed = False
        for key, value in self._DEFAULT_USER_SETTINGS.items():
            if key not in config:
                config[key] = value
                changed = True
                print(
                    f"User {self._user_id} added new default '{key}': {value}"
                )

        if changed:
            self._write(config)

        return config  # type: ignore
