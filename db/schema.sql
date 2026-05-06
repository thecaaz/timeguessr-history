-- Schema for timeguessr-history

CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY,
  date TEXT UNIQUE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screenshots (
  id INTEGER PRIMARY KEY,
  game_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  image_url TEXT,
  location_text TEXT,
  lat REAL,
  lng REAL,
  year INTEGER,
  description TEXT,
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
);
