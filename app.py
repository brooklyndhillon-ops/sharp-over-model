import requests
import math
import streamlit as st

# =========================
# CONFIG
# =========================
API_KEY = "ab53563692d9060b031c4347288d7fee"  # <-- put your real key here
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Model weights (simple, practical)
SHOT_W = 0.10
CORNER_W = 0.025

# Value threshold (edge) for calling it a bet
EDGE_THRESHOLD = 0.03  # 3%

# =========================
# HELPERS
# =========================
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
    Assumes values list is already ordered most recent -> older.
    """
    if not values:
        return 0.0
    if len(values) < 10:
        # fallback: simple average if we don't have 10
        return sum(values) / len(values)

    weights = [1.5]*5 + [1.0]*5
    return sum(v*w for v, w in zip(values[:10], weights)) / sum(weights)

# =========================
# API FUNCTIONS
# =========================
def api_get(path: str, params: dict):
    url = f"{BASE_URL}/{path}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    return r.json()

def get_team_id(team_query: str):
    """
    Safer team search:
    - If no response: show error and stop
    - If multiple: we pick the first but show the match name
    """
    data = api_get("teams", {"search": team_query})
    resp = data.get("response", [])

    if not resp:
        st.error(f"Team not found for: '{team_query}'. Try simpler name (e.g., 'Inter' not 'Inter Milan').")
        st.stop()

    team = resp[0]["team"]
    st.caption(f"Matched '{team_query}' → **{team['name']}** (team_id: {team['id']})")
    return team["id"], team["name"]

def get_last10_fixture_ids(team_id: int):
    data = api_get("fixtures", {"team": team_id, "last": 10})
    fixtures = data.get("response", [])
    # Most recent first in API-FOOTBALL usually; we’ll assume that.
    return [fx["fixture"]["id"] for fx in fixtures]

def extract_team_stat(stats_response, team_id: int, stat_type: str):
    """
    stats_response: list of teams' stats for a fixture
    returns numeric value or None
    """
    for entry in stats_response:
        if entry["team"]["id"] == team_id:
            for s in entry.get("statistics", []):
                if s.get("type") == stat_type:
                    val = s.get("value")
                    if val is None:
                        return 0
                    # Sometimes values are strings
                    try:
                        return float(val)
                    except:
                        return 0
    return None

def get_recent_weighted_shots_corners(team_id: int):
    """
    Pull last 10 fixtures → for each fixture pull statistics → extract Total Shots + Corner Kicks
    Returns weighted averages.
    """
    fixture_ids = get_last10_fixture_ids(team_id)
    if not fixture_ids:
        return 0.0, 0.0

    shots_list = []
    corners_list = []

    for fx_id in fixture_ids:
        stats_data = api_get("fixtures/statistics", {"fixture": fx_id})
        stats_resp = stats_data.get("response", [])

        shots = extract_team_stat(stats_resp, team_id, "Total Shots")
        corners = extract_team_stat(stats_resp, team_id, "Corner Kicks")

        # If a fixture has no stats, treat as 0 rather than crashing
        shots_list.append(float(shots) if shots is not None else 0.0)
        corners_list.append(float(corners) if corners is not None else 0.0)

    # Weighted average (recent form heavier)
    w_shots = weighted_average_last10(shots_list)
    w_corners = weighted_average_last10(corners_list)
    return w_shots, w_corners

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Sharp Over 2.5 Betting Model", layout="centered")
st.title("Sharp Over 2.5 Betting Model")

st.write("Enter teams + Over 2.5 American odds. App pulls last 10 match stats (shots + corners), weights recent form heavier, and outputs value edge.")

home_team_in = st.text_input("Home Team", placeholder="e.g., Bournemouth")
away_team_in = st.text_input("Away Team", placeholder="e.g., Sunderland")
odds_in = st.number_input("Over 2.5 American Odds", value=-110, step=1)

if st.button("Calculate"):
    if not API_KEY or API_KEY == "PASTE_YOUR_API_KEY_HERE":
        st.error("API key not set. Update API_KEY at the top of app.py.")
        st.stop()

    if not home_team_in or not away_team_in:
        st.error("Please enter both team names.")
        st.stop()

    # Team IDs
    home_id, home_name = get_team_id(home_team_in.strip())
    away_id, away_name = get_team_id(away_team_in.strip())

    # Pull stats
    with st.spinner("Pulling last 10 match stats (shots + corners)..."):
        home_shots, home_corners = get_recent_weighted_shots_corners(home_id)
        away_shots, away_corners = get_recent_weighted_shots_corners(away_id)

    st.subheader("Recent Form (Weighted)")
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
