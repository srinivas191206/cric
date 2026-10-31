import os
import json
import time
from datetime import datetime

TEAMS_FILE = os.path.join(os.path.dirname(__file__), "data", "teams.json")
PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "data", "players.json")
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "data", "sessions")

os.makedirs(os.path.dirname(TEAMS_FILE), exist_ok=True)

def _load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def init_default_teams_and_players():
    """Seeds default team and players matching Fulltrack AI reference and existing session data."""
    teams = _load_json(TEAMS_FILE, [])
    players = _load_json(PLAYERS_FILE, [])

    if not teams:
        teams = [
            {
                "id": "team_trajecta_squad",
                "name": "TRAJECTA Squad",
                "code": "TRJ",
                "created_at": "29 Oct 2026",
                "created_ts": 1793232000,
                "description": "Trajecta AI High Performance Bowling Squad",
                "cover_color": "linear-gradient(135deg, #0e1e38 0%, #071120 100%)"
            },
            {
                "id": "team_stumps_xi",
                "name": "Stumps XI",
                "code": "STU",
                "created_at": "25 Oct 2026",
                "created_ts": 1792886400,
                "description": "StumpVision Match & Pace Battery",
                "cover_color": "linear-gradient(135deg, #172554 0%, #0a1128 100%)"
            }
        ]
        _save_json(TEAMS_FILE, teams)

    if not players:
        players = [
            {
                "id": "player_ss",
                "team_id": "team_trajecta_squad",
                "name": "ss",
                "initials": "SS",
                "role": "Fast Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "is_admin": True
            },
            {
                "id": "player_srinuu",
                "team_id": "team_trajecta_squad",
                "name": "srinuu",
                "initials": "SR",
                "role": "Fast Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "is_admin": False
            },
            {
                "id": "player_sandy",
                "team_id": "team_trajecta_squad",
                "name": "sandy",
                "initials": "SA",
                "role": "Medium Pacer",
                "batting_style": "Right",
                "bowling_style": "Right Medium",
                "is_admin": False
            },
            {
                "id": "player_srinivas",
                "team_id": "team_trajecta_squad",
                "name": "srinivas",
                "initials": "TS",
                "role": "Pace Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "is_admin": False
            },
            {
                "id": "player_a",
                "team_id": "team_stumps_xi",
                "name": "a",
                "initials": "A",
                "role": "Fast Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "is_admin": True
            },
            {
                "id": "player_wsa",
                "team_id": "team_stumps_xi",
                "name": "wsa",
                "initials": "WS",
                "role": "Pace Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "is_admin": False
            }
        ]
        _save_json(PLAYERS_FILE, players)

    # Link existing session files with real player_id and team_id
    _migrate_existing_sessions_to_players(players)

def _migrate_existing_sessions_to_players(players):
    """Ensures every existing session has a player_id and team_id assigned."""
    if not os.path.exists(SESSIONS_DIR):
        return

    player_name_map = {p["name"].lower().strip(): p for p in players}

    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        bname = (data.get("bowler_name") or "Bowler").lower().strip()
        matched = player_name_map.get(bname)
        if not matched:
            if "ss" in bname:
                matched = player_name_map.get("ss")
            elif "srinu" in bname:
                matched = player_name_map.get("srinuu")
            elif "sandy" in bname:
                matched = player_name_map.get("sandy")
            elif "srinivas" in bname or "srini" in bname:
                matched = player_name_map.get("srinivas")
            elif "wsa" in bname:
                matched = player_name_map.get("wsa")
            elif bname == "a":
                matched = player_name_map.get("a")
            else:
                matched = player_name_map.get("ss") or players[0]

        changed = False
        if (not data.get("player_id") or data.get("player_id").startswith("player_trial") or data.get("player_id") == "player_shourya") and matched:
            data["player_id"] = matched["id"]
            changed = True
        if (not data.get("team_id") or data.get("team_id") == "team_kca_trial") and matched:
            data["team_id"] = matched["team_id"]
            changed = True

        if changed:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

def list_teams():
    init_default_teams_and_players()
    teams = _load_json(TEAMS_FILE, [])
    players = _load_json(PLAYERS_FILE, [])

    # Count players per team
    counts = {}
    for p in players:
        tid = p.get("team_id")
        counts[tid] = counts.get(tid, 0) + 1

    result = []
    for t in teams:
        t_copy = dict(t)
        t_copy["players_count"] = counts.get(t["id"], 0)
        result.append(t_copy)
    return result

def get_team(team_id: str):
    init_default_teams_and_players()
    teams = list_teams()
    for t in teams:
        if t["id"] == team_id:
            return t
    return None

def create_team(name: str, description: str = ""):
    init_default_teams_and_players()
    teams = _load_json(TEAMS_FILE, [])
    words = [w for w in name.strip().split() if w]
    code = "".join([w[0].upper() for w in words[:3]]) or "TM"
    team_id = f"team_{int(time.time())}_{os.urandom(2).hex()}"
    new_team = {
        "id": team_id,
        "name": name.strip(),
        "code": code,
        "created_at": datetime.utcnow().strftime("%d %b %Y"),
        "created_ts": int(time.time()),
        "description": description.strip() or f"{name.strip()} Squad Hub",
        "cover_color": "linear-gradient(135deg, #0e1e38 0%, #071120 100%)"
    }
    teams.append(new_team)
    _save_json(TEAMS_FILE, teams)
    new_team["players_count"] = 0
    return new_team

def list_players(team_id: str = None):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    if team_id:
        players = [p for p in players if p.get("team_id") == team_id]

    # Calculate session counts for each player
    session_counts = {}
    if os.path.exists(SESSIONS_DIR):
        for fname in os.listdir(SESSIONS_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(SESSIONS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        pid = sdata.get("player_id")
                        if pid:
                            session_counts[pid] = session_counts.get(pid, 0) + 1
                        else:
                            # match by bowler name
                            bname = (sdata.get("bowler_name") or "").lower().strip()
                            for p in players:
                                if p["name"].lower().strip() == bname:
                                    session_counts[p["id"]] = session_counts.get(p["id"], 0) + 1
                except Exception:
                    continue

    result = []
    for p in players:
        p_copy = dict(p)
        p_copy["sessions_count"] = session_counts.get(p["id"], 0)
        result.append(p_copy)
    return result

def get_player(player_id: str):
    init_default_teams_and_players()
    players = list_players()
    for p in players:
        if p["id"] == player_id:
            return p
    return None

def create_player(team_id: str, name: str, role: str = "All-rounder", batting_style: str = "Right", bowling_style: str = "Right Medium", is_admin: bool = False):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    words = [w for w in name.strip().split() if w]
    initials = "".join([w[0].upper() for w in words[:2]]) or "PL"
    player_id = f"player_{int(time.time())}_{os.urandom(2).hex()}"
    new_player = {
        "id": player_id,
        "team_id": team_id,
        "name": name.strip(),
        "initials": initials,
        "role": role,
        "batting_style": batting_style,
        "bowling_style": bowling_style,
        "is_admin": is_admin
    }
    players.append(new_player)
    _save_json(PLAYERS_FILE, players)
    new_player["sessions_count"] = 0
    return new_player

def get_player_sessions(player_id: str):
    """Returns all session cards belonging to a given player, formatted for the UI grid."""
    player = get_player(player_id)
    if not player:
        return []

    pname = player["name"].lower().strip()
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return []

    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        spid = data.get("player_id")
        sbname = (data.get("bowler_name") or "").lower().strip()

        if spid == player_id or (not spid and sbname == pname):
            deliveries = data.get("deliveries", [])
            sample_thumbnail = ""
            for d in deliveries:
                if d.get("video_url"):
                    # Use sample video or first delivery preview
                    sample_thumbnail = d.get("video_url")
                    break

            speeds = [float(d.get("speed_mph", 0.0)) for d in deliveries if d.get("speed_mph") and float(d.get("speed_mph", 0.0)) > 0]
            avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else data.get("stats", {}).get("avg_speed_mph", 0.0)
            max_speed = round(max(speeds), 1) if speeds else data.get("stats", {}).get("max_speed_mph", 0.0)

            sessions.append({
                "id": data["id"],
                "name": data["name"],
                "player_id": player_id,
                "team_id": data.get("team_id") or player.get("team_id"),
                "bowler_name": data.get("bowler_name") or player["name"],
                "deliveries_count": len(deliveries),
                "avg_speed_mph": avg_speed,
                "max_speed_mph": max_speed,
                "created_at": data.get("created_at", ""),
                "activity_note": data.get("activity_note") or f"{player['name']} Net Practice",
                "sample_video_url": sample_thumbnail
            })

    return sessions
