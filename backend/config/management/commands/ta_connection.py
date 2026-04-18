"""
Functionality:
- check that all connections are working
"""

from time import sleep

from common.src.env_settings import EnvironmentSettings
from common.src.es_connect import get_meili_client
from common.src.ta_redis import RedisArchivist
from django.core.management.base import BaseCommand, CommandError

TOPIC = """

#######################
#  Connection check   #
#######################

"""


class Command(BaseCommand):
    """command framework"""

    TIMEOUT = 120

    # pylint: disable=no-member
    help = "Check connections"

    def handle(self, *args, **options):
        """run all commands"""
        self.stdout.write(TOPIC)
        self._redis_connection_check()
        self._redis_config_set()
        self._meili_connection_check()

    def _redis_connection_check(self):
        """check if redis connection is established"""
        self.stdout.write("[1] connect to Redis")
        redis_conn = RedisArchivist().conn
        for _ in range(5):
            try:
                pong = redis_conn.execute_command("PING")
                if pong:
                    self.stdout.write(
                        self.style.SUCCESS("    ✓ Redis connection verified")
                    )
                    return

            except Exception:  # pylint: disable=broad-except
                self.stdout.write("    ... retry Redis connection")
                sleep(2)

        message = "    🗙 Redis connection failed"
        self.stdout.write(self.style.ERROR(f"{message}"))
        try:
            redis_conn.execute_command("PING")
        except Exception as err:  # pylint: disable=broad-except
            message = f"    🗙 {type(err).__name__}: {err}"
            self.stdout.write(self.style.ERROR(f"{message}"))

        sleep(60)
        raise CommandError(message)

    def _redis_config_set(self):
        """set config for redis if not set already"""
        self.stdout.write("[2] set Redis config")
        redis_conn = RedisArchivist().conn
        timeout_is = int(redis_conn.config_get("timeout").get("timeout"))
        if not timeout_is:
            redis_conn.config_set("timeout", 3600)

        self.stdout.write(self.style.SUCCESS("    ✓ Redis config set"))

    def _meili_connection_check(self):
        """wait for Meilisearch connection"""
        self.stdout.write("[3] connect to Meilisearch")
        total = self.TIMEOUT // 5
        for i in range(total):
            self.stdout.write(f"    ... waiting for Meilisearch [{i}/{total}]")
            try:
                client = get_meili_client()
                health = client.health()
                if health.get("status") == "available":
                    self.stdout.write(
                        self.style.SUCCESS(
                            "    ✓ Meilisearch connection established"
                        )
                    )
                    return
            except Exception:  # pylint: disable=broad-except
                sleep(5)
                continue

            sleep(5)

        message = "    🗙 Meilisearch connection failed"
        self.stdout.write(self.style.ERROR(f"{message}"))
        self.stdout.write(f"    MEILI_HOST: {EnvironmentSettings.MEILI_HOST}")
        sleep(60)
        raise CommandError(message)
