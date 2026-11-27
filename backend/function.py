function.py
from sqlalchemy import Integer, String, Column, create_engine, DateTime
from sqlalchemy.orm import Session, declarative_base
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


ph = PasswordHasher()
DB_PATH = "data/fantasy.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
Base = declarative_base()


ACCESS_TOKEN_EXPIRY = 30 #mins
REFRESH_TOKEN_EXPIRY = 7*24*60 #mins (7 days)
SECRET_KEY = "ipl-fantasy-cricket-league-secret-key-2026"
ALGORITHM = "HS256"


MAX_PLAYERS = 11
ROLE_LIMITS = {"batsman": 5, "bowler": 5, "all-rounder": 4, "wicketkeeper": 2}


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    user_type = Column(String, default="user")


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    role = Column(String)
    team = Column(String)
    base_points = Column(Integer)


class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    season = Column(String)


class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer)
    team1 = Column(String)
    team2 = Column(String)
    start_time = Column(DateTime)


class FantasyTeam(Base):
    __tablename__ = "fantasy_teams"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    user_id = Column(Integer)
    match_id = Column(Integer)


class TeamPlayer(Base):
    __tablename__ = "team_players"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer)
    player_id = Column(Integer)


class Contest(Base):
    __tablename__ = "contests"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    match_id = Column(Integer)


class ContestEntry(Base):
    __tablename__ = "contest_entries"
    id = Column(Integer, primary_key=True)
    contest_id = Column(Integer)
    team_id = Column(Integer)
    user_id = Column(Integer)


class PlayerStats(Base):
    __tablename__ = "player_stats"
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer)
    player_id = Column(Integer)
    points = Column(Integer)


Base.metadata.create_all(engine)


def player_details(player):
    return {
        "id": player.id,
        "name": player.name,
        "role": player.role,
        "team": player.team,
        "base_points": player.base_points
    }


def get_team_players(session, team_id):
    players = []
    links = session.query(TeamPlayer).filter_by(team_id=team_id).all()
    for link in links:
        players.append(session.get(Player, link.player_id))
    return players


def get_team_points(session, team):
    total = 0
    players = get_team_players(session, team.id)
    for player in players:
        stats = session.query(PlayerStats).filter_by(match_id=team.match_id, player_id=player.id).first()
        if stats:
            total = total + stats.points
    return total


# E11
def create_contest(name, match_id):
    session = Session(engine)
    match = session.get(Match, match_id)
    if match is None:
        session.close()
        return "match_not_found"
    contest = Contest(name=name, match_id=match_id)
    session.add(contest)
    session.commit()
    session.refresh(contest)
    response = {"message": "Contest created successfully", "contest_id": contest.id}
    session.close()
    return response


# E12
def join_contest(contest_id, team_id, user_id):
    session = Session(engine)

    contest = session.get(Contest, contest_id)
    if contest is None:
        session.close()
        return "contest_not_found"

    team = session.get(FantasyTeam, team_id)
    if team is None:
        session.close()
        return "team_not_found"
    if team.user_id != user_id:
        session.close()
        return "not_your_team"
    if team.match_id != contest.match_id:
        session.close()
        return "different_match"

    already_joined = session.query(ContestEntry).filter_by(contest_id=contest_id, team_id=team_id).first()
    if already_joined:
        session.close()
        return "already_joined"

    session.add(ContestEntry(contest_id=contest_id, team_id=team_id, user_id=user_id))
    session.commit()
    session.close()
    return "Joined contest successfully"


# E13
def publish_stats(match_id, stats_list):
    session = Session(engine)

    match = session.get(Match, match_id)
    if match is None:
        session.close()
        return "match_not_found"

    response = []
    for s in stats_list:
        player = session.get(Player, s.player_id)
        if player is None:
            session.close()
            return "player_not_found"

        # calculate fantasy points
        points = 0
        points = points + s.runs * 1
        points = points + s.fours * 1
        points = points + s.sixes * 2
        points = points + s.wickets * 25
        points = points + s.catches * 8
        points = points + s.run_outs * 12
        points = points + s.stumpings * 12

        # if stats were already published for this player, update them
        stats = session.query(PlayerStats).filter_by(match_id=match_id, player_id=s.player_id).first()
        if stats is None:
            stats = PlayerStats(match_id=match_id, player_id=s.player_id)
            session.add(stats)
        stats.points = points

        response.append({"player_id": s.player_id, "points": points})

    session.commit()
    session.close()
    return response


# E14
def get_leaderboard(contest_id):
    session = Session(engine)

    contest = session.get(Contest, contest_id)
    if contest is None:
        session.close()
        return None

    board = []
    entries = session.query(ContestEntry).filter_by(contest_id=contest_id).all()
    for entry in entries:
        team = session.get(FantasyTeam, entry.team_id)
        user = session.get(User, entry.user_id)
        points = get_team_points(session, team)
        board.append({"username": user.username, "team": team.name, "points": points})

    # highest points first
    board.sort(key=sort_by_points, reverse=True)

    rank = 1
    for row in board:
        row["rank"] = rank
        rank = rank + 1

    session.close()
    return board


def sort_by_points(row):
    return row["points"]



#----------Tokens-----------

def verify_login(username, password):
    session = Session(engine)
    user = session.query(User).filter_by(username=username).first()
    if user is None:
        session.close()
        return False
    try:
        ph.verify(user.password, password)
    except VerifyMismatchError:
        session.close()
        return False
    user_id = user.id
    user_type = user.user_type
    session.close()
    access_token = create_token(user_id=user_id, token_type="access", user_type=user_type)
    refresh_token = create_token(user_id=user_id, token_type="refresh", user_type=user_type)
    return {"access_token": access_token, "refresh_token": refresh_token, "user_type": user_type}


def create_token(user_id, token_type, user_type):
    time = ACCESS_TOKEN_EXPIRY
    if token_type == "refresh":
        time = REFRESH_TOKEN_EXPIRY
    payload = {
        "user_id": user_id,
        "token_type": token_type,
        "user_type": user_type,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=time)
    }
    token = jwt.encode(payload=payload, key=SECRET_KEY, algorithm=ALGORITHM)
    return token


def verify_token(token, token_type):
    try:
        payload = jwt.decode(jwt=token, key=SECRET_KEY, algorithms=[ALGORITHM])
    except:
        return False
    if payload["token_type"] == token_type:
        return payload
    return False


# --------Users-------------
def register_User(username, password, user_type="user"):
    session = Session(engine)
    user_exists = session.query(User).filter_by(username=username).first()
    if user_exists:
        session.close()
        return False
    session.add(User(username=username, password=ph.hash(password), user_type=user_type))
    session.commit()
    session.close()
    return True


# create one admin the first time the app runs (only admin can create organizers)
register_User(username="admin", password="admin123", user_type="admin")