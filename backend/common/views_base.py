"""base classes to inherit from"""

from common.src.es_connect import MeiliIndex
from common.src.index_generic import Pagination
from common.src.search_processor import SearchProcess, process_aggs
from rest_framework import permissions
from rest_framework.authentication import (
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.views import APIView


def check_admin(user):
    """check for admin permission for restricted views"""
    return user.is_staff or user.groups.filter(name="admin").exists()


class AdminOnly(permissions.BasePermission):
    """allow only admin"""

    def has_permission(self, request, view):
        return check_admin(request.user)


class AdminWriteOnly(permissions.BasePermission):
    """allow only admin writes"""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return permissions.IsAuthenticated().has_permission(request, view)

        return check_admin(request.user)


def _index_name_from_search_base(search_base: str) -> str:
    """derive the Meilisearch index name from the old ES search_base string.

    Examples:
      "ta_video/_search/"  -> "ta_video"
      "ta_video/_doc/"     -> "ta_video"
      "ta_channel/_doc/"   -> "ta_channel"
    """
    return search_base.split("/")[0]


class ApiBaseView(APIView):
    """base view to inherit from"""

    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    search_base = ""
    data = ""

    def __init__(self):
        super().__init__()
        self.response = {}
        # data is now a Meilisearch params dict (filter, sort, limit, offset …)
        self.data: dict = {}
        self.status_code = False
        self.context = False
        self.pagination_handler = False

    def get_document(self, document_id, progress_match=None):
        """get single document by id from Meilisearch"""
        index_name = _index_name_from_search_base(self.search_base)
        meili = MeiliIndex(index_name)
        doc = meili.get_document(document_id)
        if doc is None:
            print(f"item not found: {document_id}")
            self.status_code = 404
            return

        doc["_index"] = index_name
        try:
            self.response = SearchProcess(
                doc, match_video_user_progress=progress_match
            ).process()
        except KeyError:
            print(f"item not found: {document_id}")
            self.status_code = 404
            return

        self.status_code = 200

    def initiate_pagination(self, request):
        """set initial pagination values"""
        self.pagination_handler = Pagination(request)
        self.data["limit"] = self.pagination_handler.pagination["page_size"]
        self.data["offset"] = self.pagination_handler.pagination["page_from"]

    def get_document_list(self, request, pagination=True, progress_match=None):
        """get a list of results from Meilisearch"""
        if pagination:
            self.initiate_pagination(request)

        index_name = _index_name_from_search_base(self.search_base)
        meili = MeiliIndex(index_name)

        # pull query string out if present; remaining keys are search params
        params = dict(self.data)
        q = params.pop("q", "")

        response = meili.search(q, params)
        hits = response.get("hits", [])

        # inject _index for SearchProcess classification
        for hit in hits:
            hit["_index"] = index_name

        self.response["data"] = SearchProcess(
            hits, match_video_user_progress=progress_match
        ).process()

        if self.response["data"]:
            self.status_code = 200
        else:
            self.status_code = 404

        if pagination:
            total_hits = (
                response.get("totalHits")
                or response.get("estimatedTotalHits")
                or len(hits)
            )
            self.pagination_handler.validate(total_hits)
            self.response["paginate"] = self.pagination_handler.pagination

    def get_aggs(self):
        """stub — aggregations moved to stats/src/aggs.py"""
        self.response = {}
