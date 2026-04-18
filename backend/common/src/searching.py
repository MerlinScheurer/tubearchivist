"""
Functionality:
- handle search to populate results to view
- parse values in hit_cleanup for frontend
- calculate pagination values
"""

from common.src.es_connect import MeiliIndex
from common.src.search_processor import SearchProcess

# Meilisearch highlight tags (mirroring the old ES tags)
HIGHLIGHT_PRE = '<span class="settings-current">'
HIGHLIGHT_POST = "</span>"


class SearchForm:
    """build query from search form data"""

    def multi_search(self, search_query):
        """search across indexes, return merged results"""
        query_type, query_map = SearchParser(search_query).run()

        index = query_map.get("index", "")
        index_names = [i.strip() for i in index.split(",") if i.strip()]

        raw_results = []
        for index_name in index_names:
            hits = self._search_index(index_name, query_map)
            raw_results.extend(hits)

        search_results = SearchProcess(raw_results).process()
        all_results = self.build_results(search_results)

        return {"results": all_results, "queryType": query_type}

    @staticmethod
    def _search_index(index_name: str, query_map: dict) -> list[dict]:
        """run a search against a single Meilisearch index"""
        meili = MeiliIndex(index_name)
        q = query_map.get("term", "")

        params: dict = {"limit": 30}

        # build filter list from boolean fields
        filters = []
        if "active" in query_map:
            active_val = "true" if query_map["active"] else "false"
            field_map = {
                "ta_video": "active",
                "ta_channel": "channel_active",
                "ta_playlist": "playlist_active",
            }
            field = field_map.get(index_name)
            if field:
                filters.append(f"{field} = {active_val}")

        if "subscribed" in query_map:
            sub_val = "true" if query_map["subscribed"] else "false"
            field_map = {
                "ta_channel": "channel_subscribed",
                "ta_playlist": "playlist_subscribed",
            }
            field = field_map.get(index_name)
            if field:
                filters.append(f"{field} = {sub_val}")

        if "channel" in query_map and index_name == "ta_video":
            # channel name filter: add as attributesToSearchOn restriction
            params["attributesToSearchOn"] = ["channel.channel_name"]
            q = query_map["channel"]

        if "lang" in query_map and index_name == "ta_subtitle":
            filters.append(f"subtitle_lang = {query_map['lang'][0]}")

        if "source" in query_map and index_name == "ta_subtitle":
            filters.append(f"subtitle_source = {query_map['source'][0]}")

        if filters:
            params["filter"] = " AND ".join(filters)

        # request highlight for subtitle searches
        if index_name == "ta_subtitle":
            params["attributesToHighlight"] = ["subtitle_line"]
            params["highlightPreTag"] = HIGHLIGHT_PRE
            params["highlightPostTag"] = HIGHLIGHT_POST

        response = meili.search(q, params)

        hits = response.get("hits", [])
        # inject _index so SearchProcess can classify each result
        for hit in hits:
            hit["_index"] = index_name

        return hits

    @staticmethod
    def build_results(search_results):
        """build the all_results dict"""
        video_results = []
        channel_results = []
        playlist_results = []
        fulltext_results = []
        if search_results:
            for result in search_results:
                if result["_index"].startswith("ta_video"):
                    video_results.append(result)
                elif result["_index"].startswith("ta_channel"):
                    channel_results.append(result)
                elif result["_index"].startswith("ta_playlist"):
                    playlist_results.append(result)
                elif result["_index"].startswith("ta_subtitle"):
                    fulltext_results.append(result)

        all_results = {
            "video_results": video_results,
            "channel_results": channel_results,
            "playlist_results": playlist_results,
            "fulltext_results": fulltext_results,
        }

        return all_results


class SearchParser:
    """handle structured searches"""

    def __init__(self, search_query):
        self.query_words = search_query.lower().split()
        self.query_map: dict = {"term": [], "fuzzy": []}
        self.append_to = "term"

    def run(self) -> tuple[str, dict]:
        """parse query words, return (query_type, query_map)"""
        print(f"query words: {self.query_words}")
        query_type = self._find_map()
        self._run_words()
        self._delete_unset()
        self._match_data_types()
        print(f"query_map: {self.query_map}")
        return query_type, self.query_map

    def _find_map(self) -> str:
        """find query in keyword map"""
        first_word = self.query_words[0]
        key_word_map = self._get_map()

        if ":" in first_word:
            index_match, query_string = first_word.split(":", 1)
            if index_match in key_word_map:
                self.query_map.update(key_word_map.get(index_match))
                self.query_words[0] = query_string
                return index_match

        self.query_map.update(key_word_map.get("simple"))
        return "simple"

    @staticmethod
    def _get_map() -> dict:
        """return map to build on"""
        return {
            "simple": {
                "index": "ta_video,ta_channel,ta_playlist",
            },
            "video": {
                "index": "ta_video",
                "channel": [],
                "active": [],
            },
            "channel": {
                "index": "ta_channel",
                "active": [],
                "subscribed": [],
            },
            "playlist": {
                "index": "ta_playlist",
                "active": [],
                "subscribed": [],
            },
            "full": {
                "index": "ta_subtitle",
                "lang": [],
                "source": [],
                "channel": [],
            },
        }

    def _run_words(self) -> None:
        """append word by word"""
        for word in self.query_words:
            if ":" in word:
                keyword, search_string = word.split(":", 1)
                if keyword in self.query_map:
                    self.append_to = keyword
                    word = search_string

            if word:
                self.query_map[self.append_to].append(word)

    def _delete_unset(self) -> None:
        """delete unset keys"""
        new_query_map = {}
        for key, value in self.query_map.items():
            if value:
                new_query_map[key] = value
        self.query_map = new_query_map

    def _match_data_types(self) -> None:
        """match values with data types"""
        for key, value in self.query_map.items():
            if key in ["term", "channel"]:
                self.query_map[key] = " ".join(self.query_map[key])
            if key in ["active", "subscribed"]:
                self.query_map[key] = "yes" in value
