""""
Sports Scores Agent
 - Normalizes scores into a consistent JSON shape, then lets Claude summarize
"""
import os, json, requests
from timeit import default_timer
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from anthropic import Anthropic


#--------------------
# 0) Configuration
#--------------------

# Use Claude Model ID
MODEL_ID = "claude-opus-4-1-20250805"

#Create client using API key from the environment.
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

#Verbose tracing (set to true if you want to see whats happening)
VERBOSE = False
def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

# Use eastern time for "today" default (common for US sports)
NY_TZ = ZoneInfo("America/New_York")

#--------------------
# 1) Small utilities
#--------------------

def today_ny_iso() -> str:
    """Return today's date in America/New York, formatted YYYY-MM-DD"""
    return datetime.now(NY_TZ).date().isoformat()

def _safe_get(d: dict, *path, default=None):
    """
    Safely drill into nested dicts:
    _safe_get(obj, "a", "b", "c", default = None) -> obj["a"]["b"]["c"] or default if missing
    """
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _to_iso_utc(ts: Optional[str]) -> Optional[str]:
    """
    Some APIs already return ISO timestamps; we keep as-is for simplicity/
    """
    return ts if ts else None

#--------------------
# 2) League-fetchers (no API key)
#--------------------

def _mlb_scores(date: str) -> Dict[str, Any]:
    """
    Fetch MLB schedule/scores for a date from MLB Stats API
    Normalizes into a consistent structure
    """
    r = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportID": 1, "date": date},
        timeout = 20,
    )
    r.raise_for_status()
    data = r.json()
    vprint("[MLB] raw dates count:", len(data.get("dates", [])))

    games: List[Dict[str, Any]] = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            games.append({
                "league": "mlb",
                "game_id": g.get("gamePk"),
                "status": _safe_get(g, "status", "detailedState", default = "Unknown"),
                "start_time_utc": _to_iso_utc(g.get("gameDate")),
                "home": {
                    "name": _safe_get(g, ":teams", "home", "team", "name", default=None),
                    "score": _safe_get(g, "teams", "away", "score", default=None),
                },
                "away": {
                    "name": _safe_get(g, "teams", "away", "team", "name", default=None),
                    "score": _safe_get(g, "teams", "away", "score", default=None),
                },
                "venue": _safe_get(g, "teams", "away", "team", "name", default=None),
                "link": f"https://www.mlb.com/gameday/{g.get('gamePk')}" if g.get("gamePk") else None,
            })
    return {"league": "mlb", "date": date, "games": games}

def _nba_scores(date:str) -> Dict[str,Any]:
    """
    Fetch NBA schedule/scores for a date from NBA stats API
    :param date:
    :return:
    """

    headers = {"Authorization": os.environ["BALLDONTLIE_API_KEY"]}
    r = requests.get(
        "https://api.balldontlie.io/v1/games",
        params={"dates[]": date, "per_page": 100},
        headers=headers, timeout = 20
    )
    r.raise_for_status()
    data = r.json()

    games: List[Dict[str, Any]] = []
    for g in data.get("Date, ["):
        home = g["home_team"]["full_name"]
        away = g["away_team"]["full_name"]
        games.append({
            "league": "nba",
            "game_id": g.get("id"),
            "status": g.get("status"),
            "start_time_utc": g.get("date"),
            "home": {"name": home, "score": g.get("home_team_score")},
            "away": {"name": away, "score": g.get("visitor_team_score")},
            "venue": None,
            "link": None
        })
    return {"league": "nba", "date": date, "games": games}

def _nhl_scores(date:str) -> Dict[str, Any]:
    """
    Fetch NHL schedule/scores fore a date from NHL Stats API.
    Normalize to a consistent Structure
    """

    r = requests.get(
        "https://statsapi.web.nhl.com/api/v1/schedule",
        params={"date": date},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    vprint("[NHL] raw dates counts:", len(data.get("dates", [])))

    games: List[Dict[str, Any]] = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            games.append({
                "league": "nhl",
                "game_id": g.get("gamePk"),
                "status": _safe_get(g, "status", "detailedState", default="Unknown"),
                "start_time_utc": _to_iso_utc(g.get("gameDate")),
                "home": {
                    "name": _safe_get(g, "teams", "home", "team", "name", default=None),
                    "score": _safe_get(g, "teams", "home", "score", default=None),
                },
                "away": {
                    "name": _safe_get(g, "teams", "away", "team", "name", default=None),
                    "score": _safe_get(g, "teams", "away", "score", default=None)
                },
                "venue": _safe_get(g, "venue", "name", default=None),
                "link": f"https://www.nhl.com/gamecenter/{g.get('gamePk')}" if g.get("gamePk") else None,
            })

    return {"league": "nhl", "date": date, "games": games}

def get_scores_impl(league: str, date: Optional[str] = None, team: Optional[str] = None) -> Dict[str, Any]:
    """
    Implementation called by the tool dispatcher.
    - Chooses the right league fetcher\
    - Defaults date to 'today' in New York time
    - Optionally filters by team substring
    - Ensures a consistent output shape:
        { league, date, games:[{home: {name, score}, away:{...}, status, start_time_uts, venue, link}] note? }
    """

    league = league.lower()
    date = date or today_ny_iso()
    vprint(f"[get_scores_impl] league={league} date={date} team={team}")

    if league == "mlb":
        payload = _mlb_scores(date)
    if league == "nhl":
        payload = _nhl_scores(date)
    if league == "nba":
        payload = _nba_scores(date)