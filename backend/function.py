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

# E6
def get_tournaments():
    session = Session(engine)
    response = []
    tournaments = session.query(Tournament).all()
    for t in tournaments:
        matches = session.query(Match).filter_by(tournament_id=t.id).all()
        match_list = []
        for m in matches:
            match_list.append({
                "id": m.id,
                "team1": m.team1,
                "team2": m.team2,
                "start_time": str(m.start_time)
            })
        response.append({
            "id": t.id,
            "name": t.name,
            "season": t.season,
            "matches": match_list
        })
    session.close()
    return response


# E7
def create_team(name, match_id, user_id):
    session = Session(engine)
    match = session.get(Match, match_id)
    if match is None:
        session.close()
        return "match_not_found"
    team = FantasyTeam(name=name, match_id=match_id, user_id=user_id)
    session.add(team)
    session.commit()
    session.refresh(team)
    response = {"message": "Team created successfully", "team_id": team.id}
    session.close()
    return response

# E8
def add_player_to_team(team_id, player_id, user_id):
    session = Session(engine)

    team = session.get(FantasyTeam, team_id)
    if team is None:
        session.close()
        return "team_not_found"
    if team.user_id != user_id:
        session.close()
        return "not_your_team"

    match = session.get(Match, team.match_id)
    if datetime.now() > match.start_time:
        session.close()
        return "deadline_passed"

    player = session.get(Player, player_id)
    if player is None:
        session.close()
        return "player_not_found"

    already_added = session.query(TeamPlayer).filter_by(team_id=team_id, player_id=player_id).first()
    if already_added:
        session.close()
        return "already_added"

    players = get_team_players(session, team_id)
    if len(players) >= MAX_PLAYERS:
        session.close()
        return "team_full"

    # count players with the same role
    same_role = 0
    for p in players:
        if p.role == player.role:
            same_role = same_role + 1
    if same_role >= ROLE_LIMITS[player.role]:
        session.close()
        return "role_limit"

    session.add(TeamPlayer(team_id=team_id, player_id=player_id))
    session.commit()
    session.close()
    return "Player added to team"


# E9
def remove_player_from_team(team_id, player_id, user_id):
    session = Session(engine)

    team = session.get(FantasyTeam, team_id)
    if team is None:
        session.close()
        return "team_not_found"
    if team.user_id != user_id:
        session.close()
        return "not_your_team"

    match = session.get(Match, team.match_id)
    if datetime.now() > match.start_time:
        session.close()
        return "deadline_passed"

    link = session.query(TeamPlayer).filter_by(team_id=team_id, player_id=player_id).first()
    if link is None:
        session.close()
        return "player_not_in_team"

    session.delete(link)
    session.commit()
    session.close()
    return "Player removed from team"





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




<<<<<<< HEAD
=======
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


# E1
def create_organizer(username, password):
    return register_User(username=username, password=password, user_type="organizer")


# E2
def add_player(name, role, team, base_points):
    session = Session(engine)
    player = Player(name=name, role=role, team=team, base_points=base_points)
    session.add(player)
    session.commit()
    session.refresh(player)
    response = player_details(player)
    session.close()
    return response


# E3
def get_players():
    session = Session(engine)
    players = session.query(Player).all()
    response = [player_details(p) for p in players]
    session.close()
    return response


# E4
def get_player(player_id):
    session = Session(engine)
    player = session.get(Player, player_id)
    if player is None:
        session.close()
        return None
    response = player_details(player)
    session.close()
    return response


# E5
def create_tournament(name, season, matches):
    session = Session(engine)
    tournament = Tournament(name=name, season=season)
    session.add(tournament)
    session.commit()
    session.refresh(tournament)

    for m in matches:
        match = Match(tournament_id=tournament.id, team1=m.team1, team2=m.team2, start_time=m.start_time)
        session.add(match)
    session.commit()

    response = {"message": "Tournament created successfully", "tournament_id": tournament.id}
    session.close()
    return response
>>>>>>> 3ba9f846146da02482f43a1611a4cef4781b6631
