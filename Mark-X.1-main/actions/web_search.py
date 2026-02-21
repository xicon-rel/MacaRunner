import re
"""
SerpAPI client compatibility shim:
- Some environments provide `Client` (newer package layout),
- others provide `GoogleSearch` from `serpapi` or `google_search_results`.

This module tries imports in order and provides a uniform
`create_search_client(api_key)` factory that returns an object
with a `.search(params)` method that yields a dict.
"""
try:
    from serpapi import Client  # preferred if available
    _client_type = "Client"
except Exception:
    Client = None
    _client_type = None

if Client is None:
    try:
        # modern serpapi also exposes GoogleSearch
        from serpapi import GoogleSearch
        _client_type = "GoogleSearch_serpapi"
    except Exception:
        GoogleSearch = None
        try:
            # fallback to the older package name
            from google_search_results import GoogleSearch
            _client_type = "GoogleSearch_google_search_results"
        except Exception:
            GoogleSearch = None
from tts import edge_speak
from memory.config_manager import get_serpapi_key

MAX_NEWS_ITEMS = 3

def clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\(.*?\)|\[.*?\]", "", text)
    text = text.strip()
    text = re.sub(r"\.{2,}", ".")
    text = re.sub(r"\s*—\s*", " - ", text)
    return text

def is_trash(text: str) -> bool:
    t = text.lower()
    trash_patterns = [
        r"\bstock(?:s)?\b.*\btoday\b",
        r"\bshare(?:s)?\b.*\bprice\b",
        r"\binvestor(?:s)?\b",
        r"\btrading\b",
        r"\bmarket(?:s)?\b.*\bopen(?:s|ed)?\b",
        r"\bticker\b",
        r"\bnyse\b",
        r"\bnasdaq\b",
        r"\.\w{2,4}\sis\b",
    ]
    spam_keywords = [
        "click here", "read more", "advertisement", "sponsored",
        "subscribe", "newsletter", "sign up",
        "best things to do", "events this week", "calendar",
        "official website", "visit our", "learn more",
        "year in review", "trending now", "top 10"
    ]
    for pattern in trash_patterns:
        if re.search(pattern, t):
            return True
    return any(keyword in t for keyword in spam_keywords)

def extract_clean_news(result: dict) -> str:
    title = clean(result.get("title", ""))
    snippet = clean(result.get("snippet", ""))
    if not title:
        return ""
    if snippet.startswith(title[:30]) or snippet == title:
        return title
    if len(snippet) > 120:
        snippet = snippet[:120]
        last_period = snippet.rfind(".")
        last_space = snippet.rfind(" ")
        if last_period > 80:
            snippet = snippet[:last_period + 1]
        elif last_space > 80:
            snippet = snippet[:last_space] + "..."
        return f"{title}. {snippet}"
    return title

def format_news_output(news_items: list) -> str:
    if len(news_items) == 1:
        return news_items[0]
    elif len(news_items) == 2:
        return f"{news_items[0]}. Also, {news_items[1]}"
    else:
        result = news_items[0]
        for item in news_items[1:-1]:
            result += f". {item}"
        result += f". Additionally, {news_items[-1]}"
        return result
    
def serpapi_search(query: str) -> str:
    api_key = get_serpapi_key()
    if not api_key:
        return "Sir, the web search system is not configured."

    clean_query = query
    if "what happened" in query.lower():
        clean_query = re.sub(r"what happened (?:in|at|to)\s*", "", query, flags=re.IGNORECASE)
        clean_query += " news today"

    params = {
        "q": clean_query,
        "engine": "google_news",
        "hl": "en",
        "gl": "us",
        "num": 15
    }

    def create_search_client(key: str):
        if _client_type == "Client":
            return Client(api_key=key)
        if _client_type and _client_type.startswith("GoogleSearch") and GoogleSearch is not None:
            class _Wrapper:
                def __init__(self, key):
                    self.key = key
                def search(self, p):
                    p2 = dict(p)
                    p2["api_key"] = self.key
                    gs = GoogleSearch(p2)
                    try:
                        return gs.get_dict()
                    except Exception:
                        # some versions use get_json
                        return gs.get_json()
            return _Wrapper(key)
        raise RuntimeError("No compatible SerpAPI client available")

    try:
        client = create_search_client(api_key)
        data = client.search(params)
        results = data.get("news_results", [])
    except Exception:

        params["engine"] = "google"
        try:
            client = Client(api_key=api_key)
            data = client.search(params)
            results = data.get("organic_results", [])
        except Exception:
            return "Sir, I couldn't connect to the search service."

    if not results:
        return "Sir, I couldn't find any recent news about that."

    news_items = []
    for result in results:
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        if is_trash(title) or is_trash(snippet):
            continue
        news_text = extract_clean_news(result)
        if news_text and len(news_text.split()) >= 6:
            news_items.append(news_text)
        if len(news_items) >= MAX_NEWS_ITEMS:
            break

    if not news_items:
        return "Sir, I found some results but they weren't clear news stories."

    return format_news_output(news_items)

def web_search(parameters, player=None, session_memory=None):
    query = (parameters or {}).get("query", "").strip()
    if not query:
        msg = "Sir, I couldn't understand the search request."
        edge_speak(msg)
        return msg

    answer = serpapi_search(query)

    if player:
        player.write_log(f"AI: {answer}")

    edge_speak(answer)

    if session_memory:
        session_memory.set_last_search(query, answer)

    return answer