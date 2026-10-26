import json
import urllib.error
import urllib.request

# ESPN's public (unofficial) scoreboard endpoints, keyed by league name.
LEAGUES = {
    "nfl": "football/nfl",
    "college football": "football/college-football",
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
    "college basketball": "basketball/mens-college-basketball",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "mls": "soccer/usa.1",
    "premier league": "soccer/eng.1",
}


def _format_game(event):
    competition = event["competitions"][0]
    teams = {c["homeAway"]: c for c in competition["competitors"]}
    status = event["status"]["type"]
    return {
        "name": event["shortName"],
        "status": status["description"],
        "detail": status["shortDetail"],
        "state": status["state"],
        "home": {
            "team": teams["home"]["team"]["displayName"],
            "score": teams["home"].get("score"),
        },
        "away": {
            "team": teams["away"]["team"]["displayName"],
            "score": teams["away"].get("score"),
        },
    }


def get_scores(league="nfl", team=None):
    path = LEAGUES.get(league.strip().lower())
    if not path:
        return {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            events = json.load(response)["events"]
        games = [_format_game(event) for event in events]
    except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError):
        return {}
    if team:
        team = team.strip().lower()
        games = [
            g for g in games
            if team in g["home"]["team"].lower() or team in g["away"]["team"].lower()
        ]
    return {"league": league.strip().lower(), "games": games}


if __name__ == "__main__":
    print(json.dumps(get_scores("nfl"), indent=2))
