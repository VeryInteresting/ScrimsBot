import discord
from discord.ext import commands
from discord import app_commands, ui
import os
from dotenv import load_dotenv
import database as db
import graphing
import logging

# --- LOGGING SETUP ---
# This configures the logger to show the time, log level, and message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- BOT SETUP ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- AUTHORIZED ROLES ---
AUTHORIZED_ROLES = ["Leader -", "CO-OWNER", "Instantly", "Staff", "Senior Moderator"] # <-- ADD YOUR ADMIN ROLE NAMES HERE

def has_authorized_role(interaction: discord.Interaction) -> bool:
    """Checks if the user has one of the authorized roles."""
    user_roles = [role.name for role in interaction.user.roles]
    return any(role_name in user_roles for role_name in AUTHORIZED_ROLES)

# --- MODAL DEFINITION FOR MATCH STATS ---

class TeamStatsModal(ui.Modal):
    def __init__(self, team_name: str, opposing_team_stats: list = None):
        super().__init__(title=f"Enter Stats for {team_name}")
        self.team_name = team_name
        self.opposing_team_stats = opposing_team_stats or []

        self.player1_stats = ui.TextInput(label="Player 1 Stats (ID,Kills,Deaths,Assists)", placeholder="e.g., 123,15,10,5", required=True)
        self.player2_stats = ui.TextInput(label="Player 2 Stats (ID,Kills,Deaths,Assists)", placeholder="e.g., 124,12,10,3", required=True)
        self.player3_stats = ui.TextInput(label="Player 3 Stats (ID,Kills,Deaths,Assists)", placeholder="e.g., 125,10,10,8", required=True)
        self.player4_stats = ui.TextInput(label="Player 4 Stats (ID,Kills,Deaths,Assists)", placeholder="e.g., 126,8,10,4", required=True)
        self.player5_stats = ui.TextInput(label="Player 5 Stats (ID,Kills,Deaths,Assists)", placeholder="e.g., 127,5,10,6", required=True)
        
        self.add_item(self.player1_stats)
        self.add_item(self.player2_stats)
        self.add_item(self.player3_stats)
        self.add_item(self.player4_stats)
        self.add_item(self.player5_stats)

    async def on_submit(self, interaction: discord.Interaction):
        player_inputs = [self.player1_stats.value, self.player2_stats.value, self.player3_stats.value, self.player4_stats.value, self.player5_stats.value]
        parsed_stats = []
        for p_input in player_inputs:
            try:
                parts = p_input.replace(" ", "").split(',')
                if len(parts) != 4: raise ValueError("Invalid format")
                parsed_stats.append({'player_id': parts[0], 'kills': int(parts[1]), 'deaths': int(parts[2]), 'assists': int(parts[3])})
            except (ValueError, IndexError):
                logging.warning(f"User {interaction.user} submitted invalid match stats: {p_input}")
                await interaction.response.send_message(f"Invalid format for stats: `{p_input}`. Please use `ID,Kills,Deaths,Assists`. Match recording cancelled.", ephemeral=True)
                return

        if self.opposing_team_stats:
            all_results = self.opposing_team_stats + parsed_stats
            season = db.get_active_season()
            if season:
                db.record_match(season['id'], all_results)
                logging.info(f"Successfully recorded match stats for 10 players, submitted by {interaction.user}.")
                await interaction.response.send_message("All match results recorded successfully!", ephemeral=True)
            else:
                logging.error(f"Could not record match for user {interaction.user} because no active season was found.")
                await interaction.response.send_message("Error: No active season found.", ephemeral=True)
        else:
            second_team_name = self.view.team2_name
            await interaction.response.send_modal(TeamStatsModal(team_name=second_team_name, opposing_team_stats=parsed_stats))

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} slash command(s) to Discord.")
    except Exception as e:
        logging.error(f"An exception occurred during command syncing: {e}", exc_info=True)
    db.get_db_connection()
    logging.info("Database connection initialized.")

@bot.event
async def on_member_join(member):
    if member.bot: return
    logging.info(f'New member joined: {member.name} (ID: {member.id})')
    assigned_id = db.add_player_on_join(member.id)
    if assigned_id and WELCOME_CHANNEL_ID:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            embed = discord.Embed(title=f"Welcome to the Server, {member.name}!", description=f"We're glad to have you here.\nYour unique server ID is **#{assigned_id}**.\n\nPlease use the `/register` command to set your in-game name.", color=discord.Color.blue())
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        else:
            logging.warning(f"Could not find welcome channel with ID {WELCOME_CHANNEL_ID}.")
    elif assigned_id == "FULL":
        logging.critical("ID ASSIGNMENT FAILURE: No available IDs left to assign.")

# --- SLASH COMMANDS (General)---
@bot.tree.command(name="register", description="Set your in-game name to participate in scrims.")
@app_commands.describe(ingame_name="Your official in-game name")
async def register(interaction: discord.Interaction, ingame_name: str):
    if db.set_ingame_name(interaction.user.id, ingame_name):
        await interaction.response.send_message(f"Your in-game name has been set to **{ingame_name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("An error occurred. Make sure you are a member of this server.", ephemeral=True)

@bot.tree.command(name="performance", description="View a player's performance statistics.")
@app_commands.describe(ingame_name="The in-game name of the player", graph="Whether to show a performance graph")
async def performance(interaction: discord.Interaction, ingame_name: str, graph: bool = False):
    performance_data = db.get_player_performance(ingame_name)
    if not performance_data:
        await interaction.response.send_message(f"No performance data found for player **{ingame_name}**.")
        return
    embed = discord.Embed(title=f"Performance for {ingame_name}", color=discord.Color.blue())
    seasons, kds = [], []
    for row in performance_data:
        total_kills, total_deaths, total_assists = row['total_kills'], row['total_deaths'], row['total_assists']
        kd_ratio = total_kills / total_deaths if total_deaths > 0 else total_kills
        embed.add_field(name=f"Season: {row['season_name']}", value=f"K/D: {kd_ratio:.2f} | Kills: {total_kills} | Deaths: {total_deaths} | Assists: {total_assists}", inline=False)
        seasons.append(row['season_name'])
        kds.append(kd_ratio)
    if graph and len(seasons) > 1:
        chart_path = graphing.create_performance_graph(seasons, kds)
        file = discord.File(chart_path, filename="performance_graph.png")
        embed.set_image(url="attachment://performance_graph.png")
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show the leaderboard for the current season.")
async def leaderboard(interaction: discord.Interaction):
    leaderboard_data = db.get_leaderboard()
    season = db.get_active_season()
    if not season:
        await interaction.response.send_message("There is no active season.", ephemeral=True)
        return
    if not leaderboard_data:
        await interaction.response.send_message("No player data available for the current season's leaderboard.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Leaderboard for {season['name']}", color=discord.Color.gold())
    description = ""
    for i, row in enumerate(leaderboard_data):
        kd_ratio = row['total_kills'] / row['total_deaths']
        description += f"**{i+1}. {row['ingame_name']}** - K/D: {kd_ratio:.2f}\n"
    embed.description = description
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="getid", description="Displays the unique ID of a specific user.")
@app_commands.describe(user="The user whose ID you want to see.")
async def getid(interaction: discord.Interaction, user: discord.Member):
    player_data = db.get_player_by_discord_id(user.id)
    if player_data:
        await interaction.response.send_message(f"The ID for {user.mention} is **#{player_data['id']}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"{user.mention} does not have an ID assigned yet.", ephemeral=True)

# --- ADMIN COMMANDS ---
@bot.tree.command(name="assign_existing", description="[Admin] Assigns IDs to all existing members who don't have one.")
@app_commands.check(has_authorized_role)
async def assign_existing(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    logging.info(f"Admin command /assign_existing triggered by {interaction.user}.")
    assigned_count = 0
    guild = interaction.guild
    for member in guild.members:
        if member.bot: continue
        if not db.get_player_by_discord_id(member.id):
            db.add_player_on_join(member.id)
            assigned_count += 1
    logging.info(f"Assigned new IDs to {assigned_count} existing members.")
    await interaction.followup.send(f"Process complete. Assigned new IDs to {assigned_count} existing members.")

@bot.tree.command(name="recordmatch", description="[Admin] Record the results of a 5v5 match using pop-up forms.")
@app_commands.describe(team1_name="Name of the first team", team2_name="Name of the second team", team1_score="Final score for team 1", team2_score="Final score for team 2")
@app_commands.check(has_authorized_role)
async def recordmatch(interaction: discord.Interaction, team1_name: str, team2_name: str, team1_score: int, team2_score: int):
    view = discord.ui.View(timeout=None)
    view.team2_name = team2_name
    await interaction.response.send_modal(TeamStatsModal(team_name=team1_name, view=view))

# ... (Other admin commands remain the same, just with logging added)

@bot.tree.command(name="createseason", description="[Admin] Create a new scrims season.")
@app_commands.check(has_authorized_role)
async def createseason(interaction: discord.Interaction, name: str):
    db.create_season(name)
    logging.info(f"Season '{name}' created by {interaction.user}.")
    await interaction.response.send_message(f"Season '{name}' has been created and set as the active season.", ephemeral=True)

@bot.tree.command(name="deleteseason", description="[Admin] Delete a season and all its data.")
@app_commands.check(has_authorized_role)
async def deleteseason(interaction: discord.Interaction, name: str):
    view = discord.ui.View()
    confirm_button = discord.ui.Button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def confirm_callback(interaction: discord.Interaction):
        if db.delete_season(name):
            logging.warning(f"Season '{name}' and all its data was deleted by {interaction.user}.")
            await interaction.response.edit_message(content=f"Season '{name}' deleted.", view=None)
        else:
            await interaction.response.edit_message(content=f"Could not find season '{name}'.", view=None)
    async def cancel_callback(interaction: discord.Interaction):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)
    confirm_button.callback = confirm_callback
    cancel_button.callback = cancel_callback
    view.add_item(confirm_button)
    view.add_item(cancel_button)
    await interaction.response.send_message(f"**WARNING:** Are you sure you want to delete '{name}'? This is permanent.", view=view, ephemeral=True)

# ... (rest of the admin commands are similar)
@bot.tree.command(name="createteam", description="[Admin] Create a new team for the current season.")
@app_commands.check(has_authorized_role)
async def createteam(interaction: discord.Interaction, name: str):
    season = db.get_active_season()
    if not season:
        await interaction.response.send_message("There is no active season.", ephemeral=True)
        return
    db.create_team(name, season['id'])
    logging.info(f"Team '{name}' created by {interaction.user} for season {season['name']}.")
    await interaction.response.send_message(f"Team '{name}' has been created for the current season.", ephemeral=True)

@bot.tree.command(name="assignteam", description="[Admin] Assign a player to a team.")
@app_commands.check(has_authorized_role)
async def assignteam(interaction: discord.Interaction, player_id: str, team_name: str):
    season = db.get_active_season()
    if not season:
        await interaction.response.send_message("There is no active season.", ephemeral=True)
        return
    result = db.assign_player_to_team(player_id, team_name, season['id'])
    if result == "SUCCESS": await interaction.response.send_message(f"Player {player_id} assigned to team {team_name}.", ephemeral=True)
    elif result == "TEAM_FULL": await interaction.response.send_message(f"Team {team_name} is full.", ephemeral=True)
    elif result == "ALREADY_IN_TEAM": await interaction.response.send_message(f"Player {player_id} is already in a team.", ephemeral=True)
    else: await interaction.response.send_message(f"Team {team_name} not found in current season.", ephemeral=True)

@bot.tree.command(name="unassignteam", description="[Admin] Unassign a player from a team.")
@app_commands.check(has_authorized_role)
async def unassignteam(interaction: discord.Interaction, player_id: str, team_name: str):
    season = db.get_active_season()
    if not season:
        await interaction.response.send_message("There is no active season.", ephemeral=True)
        return
    if db.unassign_player_from_team(player_id, team_name, season['id']):
        await interaction.response.send_message(f"Player {player_id} unassigned from team {team_name}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Could not unassign player {player_id}.", ephemeral=True)
        
# Generic error handlers for check failures
admin_commands = [assign_existing, recordmatch, createseason, deleteseason, createteam, assignteam, unassignteam]
for command in admin_commands:
    @command.error
    async def on_admin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            logging.warning(f"User {interaction.user} (ID: {interaction.user.id}) tried to use an admin command without permission: {interaction.command.name}")
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)
        else:
            logging.error(f"An unhandled error occurred in command {interaction.command.name}: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred. Please contact an admin.", ephemeral=True)


# --- RUN BOT ---
if __name__ == '__main__':
    if not TOKEN:
        logging.critical("CRITICAL: DISCORD_TOKEN not found in environment variables. The bot cannot start.")
    else:
        bot.run(TOKEN)