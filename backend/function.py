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
