"""interact with queue items"""

from common.src.es_connect import IndexPaginate, MeiliIndex


class PendingInteract:
    """interact with items in download queue"""

    def __init__(self, youtube_id=False, status=False):
        self.youtube_id = youtube_id
        self.status = status

    def delete_item(self):
        """delete single item from pending"""
        MeiliIndex("ta_download").delete_document(self.youtube_id)

    def delete_bulk(self, channel_id: str | None, vid_type: str | None):
        """delete all matching items by status"""
        filter_parts = [f'status = "{self.status}"']
        if channel_id:
            filter_parts.append(f'channel_id = "{channel_id}"')
        if vid_type:
            filter_parts.append(f'vid_type = "{vid_type}"')

        filter_str = " AND ".join(filter_parts)
        MeiliIndex("ta_download").delete_documents_by_filter(filter_str)

    def update_bulk(
        self,
        channel_id: str | None,
        vid_type: str | None,
        new_status: str,
        error: bool | None = None,
    ):
        """update status in bulk — fetch matching docs then re-index"""
        filter_parts = [f'status = "{self.status}"']
        if channel_id:
            filter_parts.append(f'channel_id = "{channel_id}"')
        if vid_type:
            filter_parts.append(f'vid_type = "{vid_type}"')

        filter_str = " AND ".join(filter_parts)
        docs = IndexPaginate(
            "ta_download", {}, filter_str=filter_str
        ).get_results()

        updated = []
        for doc in docs:
            has_message = bool(doc.get("message"))

            # filter by error presence if requested
            if error is True and not has_message:
                continue
            if error is False and has_message:
                continue

            if new_status == "priority":
                doc["status"] = "pending"
                doc["auto_start"] = True
                doc["message"] = None
            elif new_status == "clear_error":
                doc["message"] = None
            else:
                doc["status"] = new_status

            updated.append(doc)

        if updated:
            MeiliIndex("ta_download").add_documents(updated)

    def update_status(self):
        """update status of a single pending item"""
        doc = MeiliIndex("ta_download").get_document(self.youtube_id)
        if not doc:
            return

        if self.status == "priority":
            doc["status"] = "pending"
            doc["auto_start"] = True
            doc["message"] = None
        else:
            doc["status"] = self.status

        MeiliIndex("ta_download").add_document(doc)

    def get_item(self):
        """return pending item dict"""
        doc = MeiliIndex("ta_download").get_document(self.youtube_id)
        if doc is None:
            return None, 404
        return doc, 200

    def get_channel(self):
        """
        get channel metadata from queue to not depend on channel to be indexed
        """
        filter_str = f'channel_id = "{self.youtube_id}"'
        results = MeiliIndex("ta_download").search(
            "", {"filter": filter_str, "limit": 1}
        )
        hits = results.get("hits", [])
        if not hits:
            channel_name = "NA"
        else:
            channel_name = hits[0].get("channel_name", "NA")

        return {
            "channel_id": self.youtube_id,
            "channel_name": channel_name,
        }
