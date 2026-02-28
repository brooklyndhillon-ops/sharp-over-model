import requests
import math
import streamlit as st

# =========================
# CONFIG
# =========================
API_KEY = "ab53563692d9060b031c4347288d7fee"  # <-- put your real API key here
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Simple practical weights
SHOT_W = 0.10
CORNER_W = 0.025

# Edge threshold for value bet call
EDGE_THRESHOLD = 0.03  # 3%

# Common league IDs (API-FOOTBALL)
LEAGUES = {
    "Premier League (England)": 39,
    "Championship (England)": 40,
    "La Liga (Spain)": 140,
    "Serie A (Italy)": 135,
    "Bundesliga (Germany)": 78,
    "Ligue 1 (France)": 61
}

# =========================
# HELPERS
# =========================
def api_get(path: str, params: dict):
    url = f"{BASE_URL}/{path}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    return r.json()

def american_to_prob(odds: float) -> float:
    odds = float(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    return 100.0 / (odds + 100.0)

def poisson_over_25(lam: float) -> float:
    # P(X >= 3) for Poisson(lam)
    p0 = math.exp(-lam)
    p1 = lam * p0
    p2 = (lam**2 / 2.0) * p0
    return 1.0 - (p0 + p1 + p2)

def expected_goals(shots: float, corners: float) -> float:
    return SHOT_W * shots + CORNER_W * corners

def weighted_average_last10(values):
    """
    Weighted last 10: first 5 (most recent) weight 1.5, older 5 weight 1.0.
    Assumes values are ordered most recent -> older.
    """
    if not values:
        return 0.0

    if len(values) < 10:
        return sum(values) / len(values)

    weights = [1.5]*5 + [1.0]*5
    return sum(v*w for v, w in zip(values[:10], weights)) / sum(weights)

def extract_team_stat(stats_response, team_id: int, stat_type: str):
    """
    stats_response: list of teams' stats for a fixture
    returns numeric value or 0 if missing
    """
    for entry in stats_response:
        if entry["team"]["id"] == team_id:
            for s in entry.get("statistics", []):
                if s.get("type") == stat_type:
                    val = s.get("value")
                    if val is None:
                        return 0.0
                    try:
                        return float(val)
                    except:
                        return 0.0
    return 0.0

# =========================
# API FUNCTIONS
# =========================
def get_team_id(team_query: str, league_id: int, season: int):
    """
    Team search restricted to a league + season so we don't match wrong countries/teams.
    """
    data = api_get("teams", {"search": team_query, "league": league_id, "season": season})
    resp = data.get("response", [])

    if not resp:
        st.error(f"Team not found in selected league/season: '{team_query}'. Try a simpler name (e.g. 'Inter').")
        st.stop()

    team = resp[0]["team"]
    st.caption(f"Matched '{team_query}' → **{team['name']}** (team_id: {team['id']})")
    return team["id"], team["name"]

def get_last10_fixture_ids(team_id: int, league_id: int, season: int):
    """
    Get last 10 fixtures for the team IN THIS league & season.
    """
    data = api_get("fixtures", {"team": team_id, "league": league_id, "season": season, "last": 10})
    fixtures = data.get("response", [])
    return [fx["fixture"]["id"] for fx in fixtures]

def get_recent_weighted_shots_corners(team_id: int, league_id: int, season: int):
    """
    Pull last 10 fixtures (league+season constrained)
    then for each fixture pull statistics and extract Total Shots + Corner Kicks.
    """
    fixture_ids = get_last10_fixture_ids(team_id, league_id, season)
    if not fixture_ids:
        return 0.0, 0.0

    shots_list = []
    corners_list = []

    for fx_id in fixture_ids:
        stats_data = api_get("fixtures/statistics", {"fixture": fx_id})
        stats_resp = stats_data.get("response", [])

        shots = extract_team_stat(stats_resp, team_id, "Total Shots")
        corners = extract_team_stat(stats_resp, team_id, "Corner Kicks")

        shots_list.append(shots)
        corners_list.append(corners)

    w_shots = weighted_average_last10(shots_list)
    w_corners = weighted_average_last10(corners_list)
    return w_shots, w_corners

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Sharp Over 2.5 Betting Model", layout="centered")
st.title("Sharp Over 2.5 Betting Model")

st.write("Select league + season, enter teams + Over 2.5 American odds. App pulls last 10 match stats (shots + corners), weights recent form heavier, and shows whether there's value.")

if not API_KEY or API_KEY == "PASTE_YOUR_API_KEY_HERE":
    st.warning("API key not set yet. Update API_KEY at the top of app.py, then redeploy.")
    st.stop()

league_name = st.selectbox("League", list(LEAGUES.keys()), index=0)
league_id = LEAGUES[league_name]
season = st.number_input("Season (YYYY)", value=2025, step=1)

home_team_in = st.text_input("Home Team", placeholder="e.g., Bournemouth")
away_team_in = st.text_input("Away Team", placeholder="e.g., Sunderland")
odds_in = st.number_input("Over 2.5 American Odds", value=-110, step=1)

if st.button("Calculate"):
    if not home_team_in or not away_team_in:
        st.error("Please enter both team names.")
        st.stop()

    # Team IDs (league + season restricted)
    home_id, home_name = get_team_id(home_team_in.strip(), league_id, int(season))
    away_id, away_name = get_team_id(away_team_in.strip(), league_id, int(season))

    with st.spinner("Pulling last 10 match stats (shots + corners)..."):
        home_shots, home_corners = get_recent_weighted_shots_corners(home_id, league_id, int(season))
        away_shots, away_corners = get_recent_weighted_shots_corners(away_id, league_id, int(season))

    st.subheader("Recent Form (Weighted last 10)")
    st.write(f"**{home_name}** — Shots: **{home_shots:.2f}**, Corners: **{home_corners:.2f}**")
    st.write(f"**{away_name}** — Shots: **{away_shots:.2f}**, Corners: **{away_corners:.2f}**")

    # Expected goals proxy
    home_xg = expected_goals(home_shots, home_corners)
    away_xg = expected_goals(away_shots, away_corners)
    lam = home_xg + away_xg

    # Probabilities
    model_prob = poisson_over_25(lam)
    market_prob = american_to_prob(odds_in)
    edge = model_prob - market_prob

    st.subheader("Model Output")
    st.write(f"Expected Goals (λ): **{lam:.2f}**")
    st.write(f"Model Probability Over 2.5: **{model_prob:.2%}**")
    st.write(f"Market Implied Probability: **{market_prob:.2%}**")
    st.write(f"Edge (Model − Market): **{edge:.2%}**")

    if edge > EDGE_THRESHOLD:
        st.success(f"VALUE BET (edge > {EDGE_THRESHOLD:.0%})")
    else:
        st.error("NO EDGE")
