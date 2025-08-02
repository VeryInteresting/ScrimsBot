import os
import psycopg2
import random

def get_db_connection():
    """Establishes a connection to the PostgreSQL database using a URL from environment variables."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise Exception("DATABASE_URL environment variable not set.")
    
    # Render requires SSL for external connections
    conn = psycopg2.connect(db_url, sslmode='require')
    return conn

def create_tables():
    """Creates the necessary database tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Use 'IF NOT EXISTS' to prevent errors on subsequent runs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seasons (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            discord_id BIGINT NOT NULL UNIQUE,
            ingame_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            season_id INTEGER,
            FOREIGN KEY (season_id) REFERENCES seasons (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER,
            player_id TEXT,
            PRIMARY KEY (team_id, player_id),
            FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS match_results (
            id SERIAL PRIMARY KEY,
            season_id INTEGER,
            player_id TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            FOREIGN KEY (season_id) REFERENCES seasons (id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

def generate_unique_id():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players")
    # Note: cursor.fetchall() returns a list of tuples
    assigned_ids = {int(row[0]) for row in cursor.fetchall()}
    all_possible_ids = set(range(1000))
    available_ids = list(all_possible_ids - assigned_ids)
    if not available_ids:
        conn.close()
        return None
    new_id = random.choice(available_ids)
    cursor.close()
    conn.close()
    return f"{new_id:03d}"

# NOTE: All following functions are updated to use '%s' placeholders for PostgreSQL
# and to correctly handle cursor/connection closing.

def add_player_on_join(discord_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM players WHERE discord_id = %s", (discord_id,))
    if cursor.fetchone():
        conn.close()
        return None
    new_id = generate_unique_id()
    if new_id is None:
        conn.close()
        return "FULL"
    cursor.execute("INSERT INTO players (id, discord_id) VALUES (%s, %s)", (new_id, discord_id))
    conn.commit()
    cursor.close()
    conn.close()
    return new_id

def set_ingame_name(discord_id, ingame_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE players SET ingame_name = %s WHERE discord_id = %s", (ingame_name, discord_id))
    updated_rows = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return updated_rows > 0

def get_player_by_discord_id(discord_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, discord_id, ingame_name FROM players WHERE discord_id = %s", (discord_id,))
    player_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if not player_data: return None
    # Manually create a dictionary-like object for consistency
    return {'id': player_data[0], 'discord_id': player_data[1], 'ingame_name': player_data[2]}

# ... (The rest of the functions are similarly updated)

def create_season(name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE seasons SET is_active = FALSE")
    cursor.execute("INSERT INTO seasons (name, is_active) VALUES (%s, TRUE)", (name,))
    conn.commit()
    cursor.close()
    conn.close()

def get_active_season():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM seasons WHERE is_active = TRUE")
    season = cursor.fetchone()
    cursor.close()
    conn.close()
    if not season: return None
    return {'id': season[0], 'name': season[1]}

def delete_season(name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM seasons WHERE name = %s", (name,))
    deleted_rows = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return deleted_rows > 0

def create_team(name, season_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO teams (name, season_id) VALUES (%s, %s)", (name, season_id))
    conn.commit()
    cursor.close()
    conn.close()

def assign_player_to_team(player_id, team_name, season_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = %s AND season_id = %s", (team_name, season_id))
    team = cursor.fetchone()
    if not team:
        conn.close()
        return "TEAM_NOT_FOUND"
    
    team_id = team[0]
    cursor.execute("SELECT count(*) FROM team_members WHERE team_id = %s", (team_id,))
    if cursor.fetchone()[0] >= 5:
        conn.close()
        return "TEAM_FULL"
        
    try:
        cursor.execute("INSERT INTO team_members (team_id, player_id) VALUES (%s, %s)", (team_id, player_id))
        conn.commit()
        cursor.close()
        conn.close()
        return "SUCCESS"
    except psycopg2.IntegrityError:
        conn.close()
        return "ALREADY_IN_TEAM"

def unassign_player_from_team(player_id, team_name, season_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM teams WHERE name = %s AND season_id = %s", (team_name, season_id))
    team = cursor.fetchone()
    if not team:
        conn.close()
        return False
    team_id = team[0]
    cursor.execute("DELETE FROM team_members WHERE team_id = %s AND player_id = %s", (team_id, player_id))
    deleted_rows = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return deleted_rows > 0

def record_match(season_id, results):
    conn = get_db_connection()
    cursor = conn.cursor()
    for result in results:
        cursor.execute("INSERT INTO match_results (season_id, player_id, kills, deaths, assists) VALUES (%s, %s, %s, %s, %s)",
                       (season_id, result['player_id'], result['kills'], result['deaths'], result['assists']))
    conn.commit()
    cursor.close()
    conn.close()

def get_player_performance(ingame_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.name, SUM(mr.kills), SUM(mr.deaths), SUM(mr.assists)
        FROM match_results mr
        JOIN players p ON mr.player_id = p.id
        JOIN seasons s ON mr.season_id = s.id
        WHERE p.ingame_name = %s
        GROUP BY s.id, s.name
        ORDER BY s.id
    """, (ingame_name,))
    performance = [{'season_name': row[0], 'total_kills': row[1], 'total_deaths': row[2], 'total_assists': row[3]} for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return performance

def get_leaderboard():
    season = get_active_season()
    if not season: return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.ingame_name, SUM(mr.kills), SUM(mr.deaths)
        FROM match_results mr
        JOIN players p ON mr.player_id = p.id
        WHERE mr.season_id = %s AND p.ingame_name IS NOT NULL
        GROUP BY p.ingame_name
        HAVING SUM(mr.deaths) > 0
        ORDER BY (CAST(SUM(mr.kills) AS REAL) / SUM(mr.deaths)) DESC
    """, (season['id'],))
    leaderboard = [{'ingame_name': row[0], 'total_kills': row[1], 'total_deaths': row[2]} for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return leaderboard