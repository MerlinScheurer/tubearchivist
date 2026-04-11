"""
functionality:
- wrapper around meilisearch client
- reusable IndexPaginate to extract an entire index
"""

from typing import Any

import meilisearch
from common.src.env_settings import EnvironmentSettings


def _doc_to_dict(doc) -> dict:
    """Convert a Meilisearch Document object (or plain dict) to a plain dict."""
    if isinstance(doc, dict):
        return doc
    # Document objects expose their fields via __dict__ or dict()
    if hasattr(doc, "__dict__"):
        return {k: v for k, v in doc.__dict__.items() if not k.startswith("_")}
    return dict(doc)


def get_meili_client() -> meilisearch.Client:
    """return a configured meilisearch Client instance"""
    return meilisearch.Client(
        EnvironmentSettings.MEILI_HOST,
        EnvironmentSettings.MEILI_MASTER_KEY,
    )


class MeiliIndex:
    """thin wrapper around a single Meilisearch index

    Provides helpers that mirror the old ElasticWrap call patterns so that
    callers can be migrated incrementally.
    """

    def __init__(self, index_name: str):
        self.index_name = index_name
        self._client = get_meili_client()
        self._index = self._client.index(index_name)

    # ------------------------------------------------------------------
    # document CRUD
    # ------------------------------------------------------------------

    def get_document(self, doc_id: str) -> dict | None:
        """fetch a single document by id, returns None when not found"""
        try:
            doc = self._index.get_document(doc_id)
            return _doc_to_dict(doc)
        except meilisearch.errors.MeilisearchApiError as exc:
            if exc.code == "document_not_found":
                return None
            raise

    def add_document(
        self, document: dict, primary_key: str | None = None
    ) -> dict:
        """add or replace a document (upsert)"""
        task = self._index.add_documents([document], primary_key=primary_key)
        return task

    def add_documents(
        self,
        documents: list[dict],
        primary_key: str | None = None,
        batch_size: int = 500,
    ) -> list[dict]:
        """add or replace multiple documents in batches"""
        task = self._index.add_documents_in_batches(
            documents,
            batch_size=batch_size,
            primary_key=primary_key,
        )
        return task

    def update_document(self, document: dict) -> dict:
        """partial update — only supplied fields are changed"""
        task = self._index.update_documents([document])
        return task

    def delete_document(self, doc_id: str) -> dict:
        """delete a single document by id"""
        task = self._index.delete_document(doc_id)
        return task

    def delete_documents_by_filter(self, filter_str: str) -> dict:
        """delete all documents matching a filter expression"""
        task = self._index.delete_documents(filter=filter_str)
        return task

    # ------------------------------------------------------------------
    # search / browse
    # ------------------------------------------------------------------

    def search(self, query: str = "", params: dict | None = None) -> dict:
        """run a search query and return the raw Meilisearch response"""
        return self._index.search(query, params or {})

    def browse(
        self, offset: int = 0, limit: int = 500, filter_str: str | None = None
    ) -> list[dict]:
        """browse documents without ranking (no query text), returns list of docs"""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if filter_str:
            params["filter"] = filter_str
        result = self._index.get_documents(params)
        # result is a DocumentsResults object; .results is a list of Document objects
        docs = result.results if hasattr(result, "results") else list(result)
        return [_doc_to_dict(d) for d in docs]

    # ------------------------------------------------------------------
    # index settings
    # ------------------------------------------------------------------

    def update_settings(self, settings: dict) -> dict:
        """update index settings (searchable/filterable/sortable attrs etc.)"""
        return self._index.update_settings(settings)

    def get_settings(self) -> dict:
        """return current index settings"""
        return self._index.get_settings()


class IndexPaginate:
    """iterate through an entire Meilisearch index page by page.

    Drop-in replacement for the old ES PIT-based IndexPaginate.

    kwargs:
    - size: int, page size (default DEFAULT_SIZE)
    - keep_source: bool, kept for compatibility — always True for Meilisearch
    - callback: obj, Class implementing run method called for every page
    - task: task object to send notification
    - total: int, total items in index for progress messages
    - filter_str: str, Meilisearch filter expression to restrict results
    """

    DEFAULT_SIZE = 500

    def __init__(self, index_name: str, data: dict, **kwargs):
        self.index_name = index_name
        self.data = data or {}
        self.kwargs = kwargs
        self._meili = MeiliIndex(index_name)

    def get_results(self) -> list[dict]:
        """return all documents from index, with optional filter"""
        return self._run_loop()

    def _run_loop(self) -> list[dict]:
        size = self.kwargs.get("size") or self.DEFAULT_SIZE
        filter_str = self.kwargs.get("filter_str") or self.data.get("filter")
        all_results: list[dict] = []
        offset = 0
        counter = 0

        while True:
            hits = self._meili.browse(
                offset=offset,
                limit=size,
                filter_str=filter_str,
            )

            if not hits:
                break

            all_results.extend(hits)

            if self.kwargs.get("callback"):
                self.kwargs["callback"](
                    hits, self.index_name, counter=counter
                ).run()

            if self.kwargs.get("task"):
                print(f"{self.index_name}: processing page {counter}")
                self._notify(len(all_results))

            counter += 1
            offset += len(hits)

            # stop when we received a partial page (last page)
            if len(hits) < size:
                break

        return all_results

    def _notify(self, processed: int) -> None:
        """send notification on task"""
        total = self.kwargs.get("total")
        progress = processed / total if total else 0
        index_clean = self.index_name.lstrip("ta_").title()
        message = [f"Processing {index_clean}s {processed}/{total}"]
        self.kwargs["task"].send_progress(message, progress=progress)
