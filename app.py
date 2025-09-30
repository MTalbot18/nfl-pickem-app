import streamlit as st
import requests
from datetime import datetime, timedelta

# Firebase config from secrets.toml
API_KEY = st.secrets["apiKey"]

# Firebase REST endpoint for email/password login
FIREBASE_AUTH_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"

# UI
from firebase_admin import credentials, firestore, initialize_app

# Initialize Firebase Admin SDK (only once)
if "firebase_admin" not in st.session_state:
    import json
    cred_dict = dict(st.secrets["firebase_service_account"])
    cred = credentials.Certificate(cred_dict)
    app = initialize_app(cred)
    st.session_state.db = firestore.client()

FIREBASE_SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"

st.title("🏈 NFL Pickem Auth")

auth_mode = st.radio("Choose mode:", ["Login", "Signup"], key="auth_mode")

email = st.text_input("Email", key="auth_email")
password = st.text_input("Password", type="password", key="auth_password")

if auth_mode == "Signup":
    name_input = st.text_input("Name", key="signup_name")
    phone_input = st.text_input("Phone Number (e.g. +18645551234)", key="signup_phone")

if st.button("Submit", key="auth_submit"):
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    try:
        if auth_mode == "Login":
            res = requests.post(FIREBASE_AUTH_URL, json=payload)
        else:
            res = requests.post(FIREBASE_SIGNUP_URL, json=payload)

        res.raise_for_status()
        user_data = res.json()
        st.session_state.user = user_data
        st.session_state.user_id = user_data["localId"]

        if auth_mode == "Signup":
            st.session_state.name = name_input
            st.session_state.db.collection("users").document(user_data["localId"]).set({
                "email": email,
                "name": name_input,
                "phone": phone_input
            })
            st.success(f"Account created for {name_input}!")
        else:
            # Fetch name from Firestore
            doc = st.session_state.db.collection("users").document(user_data["localId"]).get()
            if doc.exists:
                st.session_state.name = doc.to_dict().get("name", "")
            st.success(f"Welcome back, {st.session_state.name}!")

    except requests.exceptions.HTTPError as e:
        error_msg = res.json().get("error", {}).get("message", "Unknown error")
        st.error(f"{auth_mode} failed: {error_msg}")
        st.caption(f"Details: {e}")

# Show user info if logged in
if "user" in st.session_state:
    st.write("🔐 Authenticated user info:")
    st.json(st.session_state.user)

# --- App Logic ---
api_key = "123"

# --- Only show game logic if logged in ---
if "user_id" in st.session_state and "name" in st.session_state:
    user_id = st.session_state.user_id
    name = st.session_state.name

    def get_current_nfl_week():
        week1_start = datetime(2025, 9, 3)
        today = datetime.today()
        while today.weekday() != 2:
            today -= timedelta(days=1)
        delta = today - week1_start
        return max(1, (delta.days // 7) + 1)

    def get_weekly_matchups(api_key, week, season=2025):
        url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsround.php?id=4391&r={week}&s={season}"
        response = requests.get(url)
        try:
            data = response.json()
        except Exception as e:
            st.error(f"❌ Failed to parse JSON: {e}")
            return []

        matchups = []
        for event in data.get("events", []):
            home = event.get("strHomeTeam")
            away = event.get("strAwayTeam")
            home_logo = event.get("strHomeTeamBadge")
            away_logo = event.get("strAwayTeamBadge")
            date_str = event.get("dateEvent")
            time_str = event.get("strTime")
            if home and away and date_str and time_str:
                kickoff_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                matchups.append({
                    "matchup": f"{away} vs {home}",
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "kickoff": kickoff_dt
                })
        return matchups

    def get_mnf_score(api_key, week, season=2025):
        url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsround.php?id=4391&r={week}&s={season}"
        response = requests.get(url)
        data = response.json()
        latest_mnf = None
        latest_time = None
        for event in data.get("events", []):
            date_str = event.get("dateEvent")
            time_str = event.get("strTime")
            home = event.get("strHomeTeam")
            away = event.get("strAwayTeam")
            home_score = event.get("intHomeScore")
            away_score = event.get("intAwayScore")
            if date_str and time_str and home_score is not None and away_score is not None:
                game_date = datetime.strptime(date_str, "%Y-%m-%d")
                if game_date.weekday() == 0:
                    game_time = datetime.strptime(time_str, "%H:%M:%S").time()
                    if latest_time is None or game_time > latest_time:
                        latest_time = game_time
                        latest_mnf = {
                            "matchup": f"{away} vs {home}",
                            "score": home_score + away_score,
                            "kickoff": game_time.strftime("%I:%M %p")
                        }
        return latest_mnf

    def get_week_winners(api_key, week, season=2025):
        url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsround.php?id=4391&r={week}&s={season}"
        response = requests.get(url)
        data = response.json()
        winners = {}
        for event in data.get("events", []):
            home = event.get("strHomeTeam")
            away = event.get("strAwayTeam")
            home_score = event.get("intHomeScore")
            away_score = event.get("intAwayScore")
            if home and away and home_score is not None and away_score is not None:
                winner = home if home_score > away_score else away
                matchup = f"{away} vs {home}"
                winners[matchup] = winner
        return winners

    def submit_picks(user_id, name, picks, mnf_score, week):
        db.collection("picks").add({
            "user_id": user_id,
            "week": week,
            "name": name,
            "picks": picks,
            "mnf_score": mnf_score,
            "timestamp": datetime.now().isoformat()
        })

    def get_user_picks(user_id):
        docs = db.collection("picks").where("user_id", "==", user_id).stream()
        return [doc.to_dict() for doc in docs]

    def get_all_picks_for_week(week):
        docs = db.collection("picks").where("week", "==", week).stream()
        return [doc.to_dict() for doc in docs]

    def score_user_picks_firebase(picks, winners):
        scores = {}
        for entry in picks:
            name = entry["name"]
            mnf_guess = int(entry["mnf_score"])
            timestamp = entry["timestamp"]
            correct = 0
            for matchup, pick in entry["picks"].items():
                if winners.get(matchup) == pick:
                    correct += 1
            scores[name] = {"correct": correct, "mnf_guess": mnf_guess, "timestamp": timestamp}
        return scores

    def rank_users(scores, actual_mnf_score):
        return sorted(scores.items(), key=lambda x: (
            -x[1]["correct"],
            abs(x[1]["mnf_guess"] - actual_mnf_score),
            x[1]["timestamp"]
        ))

    # --- Run Game Logic ---
    week = get_current_nfl_week()
    games = get_weekly_matchups(api_key, week)
    mnf = get_mnf_score(api_key, week)
    actual_mnf_score = mnf["score"] if mnf else 0
    winners = get_week_winners(api_key, week)
    picks = get_all_picks_for_week(week)
    scores = score_user_picks_firebase(picks, winners)
    ranked = rank_users(scores, actual_mnf_score)

    # --- UI ---
    st.title(f"🏈 NFL Pickem - Week {week}")

    st.subheader("📋 My Picks")
    user_history = get_user_picks(user_id)
    if user_history:
        for entry in sorted(user_history, key=lambda x: x["week"], reverse=True):
            st.write(f"Week {entry['week']}:")
            for matchup, pick in entry["picks"].items():
                st.write(f"• {matchup}: {pick}")
            st.write(f"MNF guess: {entry['mnf_score']}")
            st.write("---")
    else:
        st.info("No picks submitted yet.")

    st.subheader("📝 Submit Your Picks")
    user_picks = {}
    now = datetime.now()

    for game in games:
        matchup = game["matchup"]
        team1, team2 = matchup.split(" vs ")
        kickoff = game["kickoff"]

        st.image(game["away_logo"], width=50)
        st.image(game["home_logo"], width=50)
        st.write(f"Kickoff: {kickoff.strftime('%A %I:%M %p')}")

        if now < kickoff:
            user_picks[matchup] = st.radio(f"{matchup}", [team1, team2])
        else:
            st.warning(f"⏰ Picks closed for {matchup} (kickoff passed)")

    mnf_score = st.number_input("Guess the combined score of Monday Night Football", min_value=0)

    if st.button("Submit Picks"):
        if user_picks:
            submit_picks(user_id, name, user_picks, mnf_score, week)
            st.success("✅ Your picks have been submitted!")
        else:
            st.warning("No open games to submit picks for.")

    st.subheader("🏆 Leaderboard")
   