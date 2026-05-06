from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from db import dao

app = FastAPI(title="timeguessr-history")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "games.sqlite")
# Ensure DB exists and schema initialized
dao.init_db(DB_PATH)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = dao.get_conn(DB_PATH)
    games = dao.get_games(conn)
    conn.close()
    return templates.TemplateResponse(request, "index.html", {"games": games})


@app.get("/game/{date}", response_class=HTMLResponse)
def game_view(request: Request, date: str):
    conn = dao.get_conn(DB_PATH)
    game = dao.get_game_by_date(conn, date)
    if not game:
        conn.close()
        raise HTTPException(status_code=404, detail="Game not found")
    screenshots = dao.get_screenshots_for_game(conn, game["id"])
    conn.close()
    return templates.TemplateResponse(request, "game.html", {"date": date, "screenshots": screenshots})
