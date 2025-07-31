import sqlite3
import os
import random

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    # The mount path for our persistent disk on Render
    db_dir = './data'
    db_path = os.path.join(db_dir, 'scrims.db')

    # Ensure the directory exists
    os.makedirs(db_dir, exist_ok=True)
    
    # Connect to the database at the new path
    conn = sqlite3.connect(db_path)

    # The rest is for initializing tables if the DB is new
    # Check if tables exist by querying sqlite_master
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
    if cursor.fetchone() is None:
        # If the 'players' table doesn't exist, we assume the DB is new
        create_tables(conn)

    conn.row_factory = sqlite3.Row
    return conn

def create_tables(conn):
    """Creates the necessary database tables if they don't exist."""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE players (
            id TEXT PRIMARY KEY,
            discord_id INTEGER NOT NULL UNIQUE,
            ingame_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            season_id INTEGER,
            FOREIGN KEY (season_id) REFERENCES seasons (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE team_members (
            team_id INTEGER,
            player_id TEXT,
            PRIMARY KEY (team_id, player_id),
            FOREIGN KEY (team_id) REFERENCES teams (id),
            FOREIGN KEY (player_id) REFERENCES players (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            player_id TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            FOREIGN KEY (season_id) REFERENCES seasons (id),
            FOREIGN KEY (player_id) REFERENCES players (id)
        )
    ''')
    conn.commit()

def generate_unique_id():
    """Generates a unique 3-digit ID that is not already in the players table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players")
    assigned_ids = {int(row['id']) for row in cursor.fetchall()}
    all_possible_ids = set(range(1000))
    available_ids = list(all_possible_ids - assigned_ids)
    if not available_ids:
        conn.close()
        return None
    new_id = random.choice(available_ids)
    conn.close()
    return f"{new_id:03d}"

def add_player_on_join(discord_id):
    """Adds a new member to the database and assigns them a unique ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Check if user already exists
    cursor.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
    if cursor.fetchone():
        conn.close()
        return None # User already exists
        
    new_id = generate_unique_id()
    if new_id is None:
        conn.close()
        return "FULL" # No more IDs available

    cursor.execute("INSERT INTO players (id, discord_id) VALUES (?, ?)", (new_id, discord_id))
    conn.commit()
    conn.close()
    return new_id

def set_ingame_name(discord_id, ingame_name):
    """Sets or updates a player's in-game name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE players SET ingame_name = ? WHERE discord_id = ?", (ingame_name, discord_id))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0

def get_player_by_discord_id(discord_id):
    """Retrieves a player's data using their Discord ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE discord_id = ?", (discord_id,))
    player = cursor.fetchone()
    conn.close()
    return player

def get_player_by_ingame_name(ingame_name):
    """Retrieves a player's data using their in-game name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE ingame_name = ?", (ingame_name,))
    player = cursor.fetchone()
    conn.close()
    return player

# --- All other database functions (create_season, delete_season, create_team, etc.) remain the same ---
# (You can copy them from the previous version of the ScrimsBot database.py)

def create_season(name):
    """Creates a new season and sets all others to inactive."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE seasons SET is_active = 0")
    cursor.execute("INSERT INTO seasons (name, is_active) VALUES (?, 1)", (name,))
    conn.commit()
    conn.close()

def get_active_season():
    """Gets the currently active season."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM seasons WHERE is_active = 1")
    season = cursor.fetchone()
    conn.close()
    return season

def delete_season(name):
    """Deletes a season and all associated data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM seasons WHERE name = ?", (name,))
    season = cursor.fetchone()
    if season:
        season_id = season['id']
        cursor.execute("DELETE FROM match_results WHERE season_id = ?", (season_id,))
        cursor.execute("DELETE FROM team_members WHERE team_id IN (SELECT id FROM teams WHERE season_id = ?)", (season_id,))
        cursor.execute("DELETE FROM teams WHERE season_id = ?", (season_id,))
        cursor.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
        conn.commit()
    conn.close()
    return season is not None

def create_team(name, season_id):
    """Creates a new team for a given season."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO teams (name, season_id) VALUES (?, ?)", (name, season_id))
    conn.commit()
    conn.close()

def assign_player_to_team(player_id, team_name, season_id):
    """Assigns a player to a team for the current season."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ? AND season_id = ?", (team_name, season_id))
    team = cursor.fetchone()
    if team:
        team_id = team['id']
        cursor.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,))
        member_count = cursor.fetchone()[0]
        if member_count < 5:
            try:
                cursor.execute("INSERT INTO team_members (team_id, player_id) VALUES (?, ?)", (team_id, player_id))
                conn.commit()
                return "SUCCESS"
            except sqlite3.IntegrityError:
                return "ALREADY_IN_TEAM"
        else:
            return "TEAM_FULL"
    else:
        return "TEAM_NOT_FOUND"
    conn.close()


def unassign_player_from_team(player_id, team_name, season_id):
    """Unassigns a player from a team."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = ? AND season_id = ?", (team_name, season_id))
    team = cursor.fetchone()
    if team:
        team_id = team['id']
        cursor.execute("DELETE FROM team_members WHERE team_id = ? AND player_id = ?", (team_id, player_id))
        conn.commit()
        return cursor.rowcount > 0
    conn.close()
    return False

def record_match(season_id, results):
    """Records the results of a match."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for result in results:
        cursor.execute("INSERT INTO match_results (season_id, player_id, kills, deaths, assists) VALUES (?, ?, ?, ?, ?)",
                       (season_id, result['player_id'], result['kills'], result['deaths'], result['assists']))
    conn.commit()
    conn.close()

def get_player_performance(ingame_name):
    """Gets the performance statistics for a player across all seasons."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.name as season_name, SUM(mr.kills) as total_kills, SUM(mr.deaths) as total_deaths, SUM(mr.assists) as total_assists
        FROM match_results mr
        JOIN players p ON mr.player_id = p.id
        JOIN seasons s ON mr.season_id = s.id
        WHERE p.ingame_name = ?
        GROUP BY s.name
        ORDER BY s.id
    """, (ingame_name,))
    performance = cursor.fetchall()
    conn.close()
    return performance

def get_leaderboard():
    """Gets the K/D ratio for all players in the current season."""
    season = get_active_season()
    if not season:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.ingame_name, SUM(mr.kills) as total_kills, SUM(mr.deaths) as total_deaths
        FROM match_results mr
        JOIN players p ON mr.player_id = p.id
        WHERE mr.season_id = ? AND p.ingame_name IS NOT NULL
        GROUP BY p.ingame_name
        HAVING SUM(mr.deaths) > 0
        ORDER BY (CAST(SUM(mr.kills) AS REAL) / SUM(mr.deaths)) DESC
    """, (season['id'],))
    leaderboard = cursor.fetchall()
    conn.close()
    return leaderboard