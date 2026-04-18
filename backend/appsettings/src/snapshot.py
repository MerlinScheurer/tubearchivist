"""
Snapshot functionality was specific to Elasticsearch SLM.
Meilisearch does not have an equivalent snapshot/restore mechanism.
This module is stubbed out — all methods are no-ops or return False.
"""


class ElasticSnapshot:
    """stub — ES SLM snapshots are not supported with Meilisearch"""

    def setup(self):
        """no-op: snapshot setup not applicable"""
        print("snapshot: skipped (not supported with Meilisearch)")

    def get_snapshot_stats(self):
        """return empty snapshot info"""
        return False

    def get_single_snapshot(self, snapshot_id):
        """return not-found"""
        return False

    def take_snapshot_now(self, wait=False):
        """no-op"""
        print("snapshot: take_snapshot_now — not supported with Meilisearch")
        return {}

    def restore_all(self, snapshot_name):
        """no-op"""
        print("snapshot: restore_all — not supported with Meilisearch")
        return False

    def delete_single_snapshot(self, snapshot_id):
        """no-op"""
        print(
            "snapshot: delete_single_snapshot — not supported with Meilisearch"
        )
        return False
