from fastapi import FastAPI, HTTPException, Header, Body
from datetime import datetime
from pydantic import BaseModel, Field
import function


app = FastAPI()

PLAYER_ROLES = ["batsman", "bowler", "all-rounder", "wicketkeeper"]
ALL_ROLES = ["admin", "organizer", "user"]


def check_role(token, allowed_roles):
    payload = function.verify_token(token=token, token_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload["user_type"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="Permission denied")
    return payload


class UserIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1)
    role: str
    team: str = Field(min_length=1)
    base_points: int = Field(ge=0)


class MatchCreate(BaseModel):
    team1: str = Field(min_length=1)
    team2: str = Field(min_length=1)
    start_time: datetime


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1)
    season: str = Field(min_length=1)
    matches: list[MatchCreate]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1)
    match_id: int


class ContestCreate(BaseModel):
    name: str = Field(min_length=1)
    match_id: int


class JoinContest(BaseModel):
    team_id: int


class PlayerStats(BaseModel):
    player_id: int
    runs: int = Field(default=0, ge=0)
    fours: int = Field(default=0, ge=0)
    sixes: int = Field(default=0, ge=0)
    wickets: int = Field(default=0, ge=0)
    catches: int = Field(default=0, ge=0)
    run_outs: int = Field(default=0, ge=0)
    stumpings: int = Field(default=0, ge=0)


#----------Auth-----------

# A1
@app.post("/auth/register")
def register_user(user: UserIn):
    if function.register_User(username=user.username, password=user.password):
        return {"message": "User registered successfully"}
    raise HTTPException(status_code=400, detail="User already exists")


# A2
@app.post("/auth/login")
def login(username=Body(), password=Body()):
    token = function.verify_login(username=username, password=password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return token


# A3
@app.post("/auth/refresh")
def refresh_token(refresh_token=Header(None)):
    payload = function.verify_token(token=refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    access_token = function.create_token(user_id=payload["user_id"], token_type="access", user_type=payload["user_type"])
    return {"access_token": access_token}


# E1
@app.post("/organizers")
def create_organizer(user: UserIn, token=Header(None)):
    check_role(token, ["admin"])
    if function.create_organizer(user.username, user.password):
        return {"message": "Organizer created successfully"}
    raise HTTPException(status_code=400, detail="User already exists")



# E2
@app.post("/players")
def add_player(player: PlayerCreate, token=Header(None)):
    check_role(token, ["organizer"])
    if player.role not in PLAYER_ROLES:
        raise HTTPException(status_code=400, detail="role must be batsman, bowler, all-rounder or wicketkeeper")
    return function.add_player(player.name, player.role, player.team, player.base_points)


# E3
@app.get("/players")
def get_players(token=Header(None)):
    check_role(token, ALL_ROLES)
    return function.get_players()


# E4
@app.get("/players/{player_id}")
def get_player(player_id: int, token=Header(None)):
    check_role(token, ALL_ROLES)
    response = function.get_player(player_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return response


# E5
@app.post("/tournaments")
def create_tournament(tournament: TournamentCreate, token=Header(None)):
    check_role(token, ["organizer"])
    return function.create_tournament(tournament.name, tournament.season, tournament.matches)
