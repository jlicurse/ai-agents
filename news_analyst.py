import json, os, time, urllib.parse
from tkinter.font import names
from typing import List, Dict, Any
import feedparser
import trafilatura
import requests
from anthropic import Anthropic
from six import text_type

MODEL_ID = "claude-opus-4-1-20250805" #claude model
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY")) #API key

#---- Tool: search news via Google News RSS (no api key), optional full text fetch ----
tools = [
    { "name": "search_news",
      "description": (
          "Search recent news across many outlets via Google News RSS and (optionally)"
          "download article text for analysis. Returns diverse sources for balanced coverage."
      ),
      "input_schema": {
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "Topic or key words (e.g>, 'NHL salary cap', 'Tesla earnings')."},
              "max_results": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8},
              "include_full_text": {"type": "boolean", "default": False},
          },
          "required": ["query"],
        },
    }
]

def _clean_text(s: str | None) -> str | None:
    if not s: return s
    return " ".join(s.split())

def download_main_text(url: str, timeout: int =15) -> str | None:
    """Try to fetch and extract main article text. Best Effort."""
    try:
# trafilatura can fetch itself, but we stream to control timeout
        r = requests.get(url, timeout=timeout, headers ={ "User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        extracted = trafilatura.extract(r.text, favor_recall=True)
        return _clean_text(extracted)
    except Exception:
        return None

def search_news_impl(query:str, max_results: int = 8, include_full_text: bool = False) -> Dict[str, Any]:
    """
    Use Google News RSS to retrieve recent coverage. No API key required.
    NOTE: Links often redirect; most browsers follow them fine. We include original link as-is.
    """
#Build Google News RS URL
    q = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

    feed = feedparser.parse(rss_url)
    items = []
    seen_titles = set()

    for entry in feed.entries[: max_results * 2]: #overfetch a bit, then dedupe
        title = _clean_text(getattr(entry, "title", "")) or "(no title)"
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())
        link = getattr(entry, "link", None) or getattr(entry, "id", None)
        summary = _clean_text(getattr(entry,"summary", "")) #RSS Snippet
        #published time (RFC822 tuple) -> ISO String if possible
        if getattr(entry, "published_parsed", None):
            published_iso = time.strftime("%Y-%m-%dT%H:%M:%S", entry.published_parsed)

        #Source (publisher - feedparser often exposes entry.source.title; fallback to domain-ish guess
        source = None
        if hasattr(entry, "source") and getattr(entry.source, "title", None):
            source = _clean_text(entry.source.title)
        if not source and link:
            try:
                source = urllib.parse.urlparse(link).netloc or None
            except Exception:
                source = None

        article = {
            "title": title,
            "url": link,
            "source": source,
            "published": published_iso,
            "snippet": summary,
        }

        if include_full_text and link:
            article_text = download_main_text(link)
            if article_text:
                article["content"] = article_text

        items.append(article)
        if len(items) >= max_results:
            break

    return {
        "query": query,
        "count": len(items),
        "articles": items
    }

def call_tool(name: str, tool_input: dict):
    if name == "search_news":
        return search_news_impl(
            tool_input["query"],
            tool_input.get("max_results", 8),
            tool_input.get("include_full_text", False),

        )
    raise ValueError(f"Unkown tool: {name}")

SYSTEM_PROMPT = """You are a careful News Analyst.
- Use the provided articles ONLY; do not invent facts or quotes.
- Compare coverage across outlets: agreements, disagreements, what’s new, what’s uncertain.
- Build a short timeline (most recent first) if dates are present.
- Call out biases, missing context, and what to watch next.
- Cite sources inline like [Source - Title] with links when available.
- Keep it concise and useful."""

def ask_news_agent(user_query: str) -> str:
    messages = [{"role": "user", "content": user_query}]
    #First turn - model decides whether to call search_news
    resp = client.messages.create(
        model = MODEL_ID,
        system = SYSTEM_PROMPT,
        max_tokens = 900,
        tools = tools,
        messages = messages
    )

    #Did Claude ask to use tools?
    tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
    if not tool_uses:
        #No tool needed; just return the answer
        text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(text_parts).strip()

    tool_results_blocks: List[Dict[str, Any]] = []
    for tu in tool_uses:
        out = call_tool(tu.name, tu.input)
        tool_results_blocks.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "content": [{"type": "text", "text": json.dumps(out)}] # Must be string or content blocks
        })

    messages.extend([
        {"role": "assistant", "content": resp.content},
        {"role": "user", "content": tool_results_blocks},
    ])

    final = client.messages.create(
        model = MODEL_ID,
        system = SYSTEM_PROMPT,
        max_tokens = 1200,
        tools = tools,
        messages = messages
    )

    text_parts = [b.text for b in final.content if getattr(b, "type", None ) == "text"]
    return "\n".join(text_parts).strip()

if  __name__ == "__main__":
    try:
        print("News Analyst ready. Ask things like:")
        print("- Compare coverage of 'Boeing deliveries Q3'")
        print(" - What are outlets saying about 'NHL expansion?' Include full text.")
        print("- Summarize 'US inflation report August' and disagreements")
        while True:
            q = input("|nAsk (or 'quit'): "). strip()
            if q.lower() in {"quit", "exit"}:
                break
            #Simple hint: say "Include full text" in your question if you want deeper summaries.
            print("\n" + ask_news_agent(q) + "\n")
    except Exception as e:
        print("Error: ", e)



