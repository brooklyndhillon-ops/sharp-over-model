import requests
import math
import streamlit as st

API_KEY = "ab53563692d9060b031c4347288d7fee"
BASE_URL = "https://v3.football.api-sports.io"

HEADERS = {
    "x-apisports-key": API_KEY
}

def american_to_prob(odds):
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)

def poisson_over_25(lam):
    p0 = math.exp(-lam)
    p1 = lam * p0
    p2 = (lam**2 / 2) * p0
    return 1 - (p0 + p1 + p2)

def weighted_average(values):
    weighted = []
    for i, v in enumerate(values):
        if i < 5:
            weighted.append(v * 1.5)
        else:
            weighted.append(v)
    return sum(weighted) / (5*1.5 + 5)

def get_team_id(team_name):
    url = f"{BASE_URL}/teams?search={team_name}"
    r = requests.get(url, headers=HEADERS).json()
    return r["response"][0]["team"]["id"]

def get_recent_stats(team_id):
    url = f"{BASE_URL}/fixtures?team={team_id}&last=10"
    r = requests.get(url, headers=HEADERS).json()
    fixtures = r["response"]

    shots = []
    corners = []

    for match in fixtures:
        fixture_id = match["fixture"]["id"]
        stats_url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
        stats = requests.get(stats_url, headers=HEADERS).json()["response"]

        for team_stats in stats:
            if team_stats["team"]["id"] == team_id:
                for stat in team_stats["statistics"]:
                    if stat["type"] == "Total Shots":
                        shots.append(stat["value"] or 0)
                    if stat["type"] == "Corner Kicks":
                        corners.append(stat["value"] or 0)

    return weighted_average(shots), weighted_average(corners)

def expected_goals(shots, corners):
    return 0.10 * shots + 0.025 * corners

st.title("Sharp Over 2.5 Betting Model")

home_team = st.text_input("Home Team")
away_team = st.text_input("Away Team")
odds = st.number_input("Over 2.5 American Odds", value=-110)

if st.button("Calculate"):
    home_id = get_team_id(home_team)
    away_id = get_team_id(away_team)

    home_shots, home_corners = get_recent_stats(home_id)
    away_shots, away_corners = get_recent_stats(away_id)

    home_xg = expected_goals(home_shots, home_corners)
    away_xg = expected_goals(away_shots, away_corners)

    lam = home_xg + away_xg

    model_prob = poisson_over_25(lam)
    market_prob = american_to_prob(odds)
    edge = model_prob - market_prob

    st.write(f"Expected Goals (λ): {lam:.2f}")
    st.write(f"Model Probability Over 2.5: {model_prob:.2%}")
    st.write(f"Market Probability: {market_prob:.2%}")
    st.write(f"Edge: {edge:.2%}")

    if edge > 0.03:
        st.success("VALUE BET")
    else:
        st.error("NO EDGE")
