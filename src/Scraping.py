# -*- coding: utf-8 -*-
"""
Created on Sun Aug 28 09:48:00 2016

@author: Matt
"""

from lxml import html
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
import os

hockey_teams_dict = {'Calgary Flames':'CGY', 'Edmonton Oilers':'EDM', 'Pittsburgh Penguins':'PIT',
'San Jose Sharks':'SJS', 'Winnipeg Jets':'WPG', 'Arizona Coyotes':'ARI',
'Nashville Predators':'NSH', 'Montreal Canadiens':'MTL', 'Minnesota Wild':'MIN',
'Philadelphia Flyers':'PHI', 'Colorado Avalanche':'COL', 'Washington Capitals':'WSH',
'New York Islanders':'NYI', 'Vegas Golden Knights':'VEG', 'Florida Panthers':'FLA',
'Columbus Blue Jackets':'CBJ', 'Tampa Bay Lightning':'TBL', 'Buffalo Sabres':'BUF',
'Detroit Red Wings':'DET', 'Dallas Stars':'DAL', 'New York Rangers':'NYR',
'New Jersey Devils':'NJD', 'St. Louis Blues':'STL', 'Chicago Blackhawks':'CHI',
'Ottawa Senators':'OTT', 'Boston Bruins':'BOS', 'Anaheim Ducks':'ANA',
'Toronto Maple Leafs':'TOR', 'Carolina Hurricanes':'CAR', 'Vancouver Canucks':'VAN',
'Los Angeles Kings':'LAK'}


# Updates player performance file given a schedule of games
def update_player_perf(schedule, old_perf_fn, sport):
    old_perf = pd.read_csv(old_perf_fn)
    if len(schedule)==0:
        return pd.DataFrame(columns=old_perf.columns)

    new_perf = pd.DataFrame()
    for i, game in schedule.iterrows():
        home_team = game['Home Team']
        away_team = game['Visitor Team']
        box = game['Box Score']
        game_dt = game['Date']
        if sport == 'NHL':
            game_perf = get_nhl_perf(box, home_team, away_team)
        elif sport == 'NBA':
            game_perf = get_nba_perf(box, home_team, away_team)
        elif sport == 'MLB':
            game_perf = get_mlb_perf(box, home_team, away_team)
        game_perf['Date'] = game_dt
        new_perf = new_perf.append(game_perf).reset_index(drop=True)

    total_perf = old_perf.append(new_perf).reset_index(drop=True)

    # De-duping perf
    match_conditions = ['Player', 'Team', 'Date']
    if sport=='NHL':
        match_conditions = match_conditions + ['Skater']
    elif sport=='MLB':
        match_conditions = match_conditions + ['Batter']
    total_perf = total_perf.drop_duplicates(subset=match_conditions)

    total_perf.to_csv(old_perf_fn, index=False)
    return new_perf

# Updates team performance file given a schedule of games
def update_team_perf(schedule, old_perf_fn, sport):
    old_perf = pd.read_csv(old_perf_fn)
    if len(schedule)==0:
        return pd.DataFrame(columns=old_perf.columns)

    new_perf = pd.DataFrame()
    for i, game in schedule.iterrows():
        home_team = game['Home Team']
        away_team = game['Visitor Team']
        box = game['Box Score']
        game_dt = game['Date']
        if sport == 'NBA':
            game_perf = get_nba_team_perf(box, home_team, away_team)
        game_perf['Date'] = game_dt
        new_perf = new_perf.append(game_perf).reset_index(drop=True)

    total_perf = old_perf.append(new_perf).reset_index(drop=True)

    # De-duping perf
    match_conditions = ['Team', 'Date']
    total_perf = total_perf.drop_duplicates(subset=match_conditions)

    total_perf.to_csv(old_perf_fn, index=False)
    return new_perf


def get_mlb_perf(url, home_full, away_full):
    # pause to prevent overloading website
    pause(5)

    page = requests.get('https://www.baseball-reference.com' + url)

    # home = convert_mlb_team(home_full)
    # away = convert_mlb_team(away_full)

    #gets batting stats
    batting_home = page.text.split('table class="sortable stats_table')[2]
    batting_home = '<table class="sortable stats_table' + batting_home + '/table>'
    batting_home_soup = BeautifulSoup(batting_home, 'lxml')
    home_batters = parse_hitter(batting_home_soup)
    home_batters['Team'] = home_full
    home_batters['Opp Team'] = away_full

    batting_away = page.text.split('table class="sortable stats_table')[1]
    batting_away = '<table class="sortable stats_table' + batting_away + '/table>'
    batting_away_soup = BeautifulSoup(batting_away, 'lxml')
    away_batters = parse_hitter(batting_away_soup)
    away_batters['Team'] = away_full
    away_batters['Opp Team'] = home_full

    # #gets pitcher stats
    pitching_home = page.text.split('table class="sortable stats_table')[4]
    pitching_home_soup = BeautifulSoup(pitching_home, 'lxml')
    home_pitchers = parse_pitcher(pitching_home_soup)
    home_pitchers['Team'] = home_full
    home_pitchers['Opp Team'] = away_full

    pitching_away = page.text.split('table class="sortable stats_table')[3]
    pitching_away_soup = BeautifulSoup(pitching_away, 'lxml')
    away_pitchers = parse_pitcher(pitching_away_soup)
    away_pitchers['Team'] = away_full
    away_pitchers['Opp Team'] = home_full

    wp_soup = BeautifulSoup(page.content, 'lxml')
    winning_pitcher = parse_pitcher_wins(wp_soup)

    #prepares batter and pitcher data and then joins
    batters = home_batters.append(away_batters).reset_index(drop=True)
    batters['Batter'] = 1
    batters_details = parse_hitter_details(batters)
    batters_details['1B'] = batters_details['Hits'] - (batters_details['2B'] + batters_details['3B'] + batters_details['HR'])

    pitchers = home_pitchers.append(away_pitchers).reset_index(drop=True)
    pitchers['Batter'] = 0
    pitchers['Win'] = [1 if p==winning_pitcher else 0 for p in pitchers['Player']]
    pitchers['QS'] = [1 if (sp==1 and ip>=6 and er<=3) else 0 for sp, ip, er in zip(pitchers['SP'], pitchers['IP'], pitchers['ER'])]
    pitchers['Outs'] = [3*round(ip,0) + round(10*(ip%1),0) for ip in pitchers['IP']]

    player_df = batters_details.append(pitchers).reset_index(drop=True)
    player_df = player_df.fillna(0)

    return player_df


def get_nhl_perf(url, home_full, away_full):
    # pause to prevent overloading website
    pause(5)

    page = requests.get('http://www.hockey-reference.com' + url)
    tree = html.fromstring(page.content)
    soup = BeautifulSoup(page.content, "lxml")

    home = hockey_teams_dict[home_full]
    away = hockey_teams_dict[away_full]

    home_tables = soup.findAll(id='%s_skaters' %home)
    home_df = parse_skaters(home_tables)
    home_df['Home'] = 'Home'
    home_df['Team'] = home_full
    home_df['Opp Team'] = away_full
    home_adv_df = parse_skaters_adv(page.text, home)
    home_all_df = pd.merge(home_df, home_adv_df, on='Player')

    away_tables = soup.findAll(id='%s_skaters' %away)
    away_df = parse_skaters(away_tables)
    away_df['Home'] = 'Away'
    away_df['Team'] = away_full
    away_df['Opp Team'] = home_full
    away_adv_df = parse_skaters_adv(page.text, away)
    away_all_df = pd.merge(away_df, away_adv_df, on='Player')

    skaters_df = home_all_df.append(away_all_df).reset_index(drop=True)
    skaters_df['Skater'] = 1

    home_goalie_table = soup.findAll(id='all_%s_goalies' %home)
    home_g_df = parse_goalies(home_goalie_table)
    home_g_df['Home'] = 'Home'
    home_g_df['Team'] = home_full
    home_g_df['Opp Team'] = away_full

    away_goalie_table = soup.findAll(id='all_%s_goalies' %away)
    away_g_df = parse_goalies(away_goalie_table)
    away_g_df['Home'] = 'Away'
    away_g_df['Team'] = away_full
    away_g_df['Opp Team'] = home_full

    goalies_df = home_g_df.append(away_g_df).reset_index(drop=True)
    goalies_df['Skater'] = 0

    player_df = skaters_df.append(goalies_df).reset_index(drop=True)

    return player_df


# Returns a DF of box score data given a url
def get_nba_perf(url, home_full, away_full):
    # pause to prevent overloading website
    pause(5)

    page = requests.get('http://' + url)
    tree = html.fromstring(page.content)
    soup = BeautifulSoup(page.content, "lxml")

    away = convert_nba_team(away_full).upper()
    home = convert_nba_team(home_full).upper()

    home_tables = soup.findAll(id='all_box-%s-game-basic' %home)
    home_df = parse_nba_basic(home_tables)
    home_df['Home'] = 'Home'
    home_df['Team'] = home_full
    home_df['Opp Team'] = away_full

    away_tables = soup.findAll(id='all_box-%s-game-basic' %away)
    away_df = parse_nba_basic(away_tables)
    away_df['Home'] = 'Away'
    away_df['Team'] = away_full
    away_df['Opp Team'] = home_full

    player_basic_df = home_df.append(away_df).reset_index(drop=True)

    home_adv_tables = soup.findAll(id='all_box-%s-game-advanced' %home)
    home_adv_df = parse_nba_adv(home_adv_tables)

    away_adv_tables = soup.findAll(id='all_box-%s-game-advanced' %away)
    away_adv_df = parse_nba_adv(away_adv_tables)

    player_adv_df = home_adv_df.append(away_adv_df).reset_index(drop=True)

    player_df = pd.merge(left=player_basic_df, right=player_adv_df, on='Player')

    return player_df



# Returns a DF of box score data given a url
def get_nba_team_perf(url, away_full, home_full):
    # pause to prevent overloading website
    pause(5)

    page = requests.get('http://' + url)
    tree = html.fromstring(page.content)
    soup = BeautifulSoup(page.content, "lxml")

    away = convert_nba_team(away_full).upper()
    home = convert_nba_team(home_full).upper()

    home_tables = soup.findAll(id='all_box-%s-game-basic' %home)
    home_df = parse_nba_team_basic(home_tables)
    home_df['Team'] = home_full

    home_adv_tables = soup.findAll(id='all_box-%s-game-advanced' %home)
    home_adv_df = parse_nba_team_adv(home_adv_tables)
    home_adv_df['Team'] = home_full

    home_all_df = pd.merge(home_df, home_adv_df, on='Team')
    home_all_df['Home'] = 'Home'
    home_all_df['Opp Team'] = away_full

    away_tables = soup.findAll(id='all_box-%s-game-basic' %away)
    away_df = parse_nba_team_basic(away_tables)
    away_df['Team'] = away_full

    away_adv_tables = soup.findAll(id='all_box-%s-game-advanced' %away)
    away_adv_df = parse_nba_team_adv(away_adv_tables)
    away_adv_df['Team'] = away_full

    away_all_df = pd.merge(away_df, away_adv_df, on='Team')
    away_all_df['Home'] = 'Away'
    away_all_df['Opp Team'] = home_full

    team_df = home_all_df.append(away_all_df).reset_index(drop=True)

    return team_df


def parse_skaters(table):
    df = pd.DataFrame()
    idx = 0
    if len(table) == 0:
        return 'Table is empty'
    for row in table[0].findAll('tr'):
        if row.find('a') is not None:

            cols = row.findAll('td')
            if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
                values = [0]*16
            else:
                values = [x.get_text() for x in cols]
            df.set_value(idx, 'Player', values[0])
            df.set_value(idx, 'Goals', values[1])
            df.set_value(idx, 'Assists', values[2])
            df.set_value(idx, 'PTS', values[3])
            df.set_value(idx, 'PM', values[4])
            df.set_value(idx, 'PIM', values[5])
            df.set_value(idx, 'EV_G', values[6])
            df.set_value(idx, 'PP_G', values[7])
            df.set_value(idx, 'SH_G', values[8])
            df.set_value(idx, 'GW_G', values[9])
            df.set_value(idx, 'EV_A', values[10])
            df.set_value(idx, 'PP_A', values[11])
            df.set_value(idx, 'SH_A', values[12])
            df.set_value(idx, 'Shots', values[13])
            df.set_value(idx, 'SPER', values[14])
            df.set_value(idx, 'TOI', values[15])

            idx += 1
    df.fillna(0)
    return df


def parse_goalies(table):
    df = pd.DataFrame()
    idx = 0
    for row in table[0].findAll('tr'):
        if row.find('a') is not None:
            cols = row.findAll('td')
            if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
                values = [0]*7
            else:
                values = [x.get_text() for x in cols]
            df.set_value(idx, 'Player', values[0])
            df.set_value(idx, 'DEC', values[1])
            df.set_value(idx, 'GA', values[2])
            df.set_value(idx, 'SA', values[3])
            df.set_value(idx, 'Saves', values[4])
            df.set_value(idx, 'SavePer', values[5])
            df.set_value(idx, 'SO', values[6])

            idx += 1
    df.fillna(0)
    return df


def parse_skaters_adv(text, team):
    tables = text.split('table')
    for t in tables:
        if '"%s_adv"' %team in t:
            adv_table = t
    adv_table = '<table' + adv_table + '/table>'
    soup = BeautifulSoup(adv_table, 'lxml')
    return parse_skaters_adv_helper(soup)

def parse_skaters_adv_helper(table):
    df = pd.DataFrame()
    idx = 0
    for row in table.findAll('tr'):
        if row.find('a') is not None:
            if row['class'] == ['ALLAll']:
                df.set_value(idx, 'Player', str(row.find('a')).split('>')[1].split('<')[0])
                cols = row.findAll('td')
                if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
                    values = [0]*10
                else:
                    values = [x.get_text() for x in cols]
                df.set_value(idx, 'Blocks', values[9])

                idx += 1
    return df


# Returns a DF of cleaned up data values for basic box score given table soup
def parse_nba_basic(table):
    df = pd.DataFrame()
    idx = 0
    for row in table[0].findAll('tr'):
        if row.find('a') is not None:
            df.set_value(idx, 'Player', str(row.find('a')).split('>')[1].split('<')[0])

            cols = row.findAll('td')
            if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
                values = [0]*20
            else:
                values = [x.get_text() for x in cols]

            df.set_value(idx, 'Minutes', values[0])
            df.set_value(idx, 'FG', values[1])
            df.set_value(idx, 'FGA', values[2])
            df.set_value(idx, 'FGP', values[3])
            df.set_value(idx, '3P', values[4])
            df.set_value(idx, '3PA', values[5])
            df.set_value(idx, '3PP', values[6])
            df.set_value(idx, 'FT', values[7])
            df.set_value(idx, 'FTA', values[8])
            df.set_value(idx, 'FTP', values[9])
            df.set_value(idx, 'ORB', values[10])
            df.set_value(idx, 'DRB', values[11])
            df.set_value(idx, 'TRB', values[12])
            df.set_value(idx, 'AST', values[13])
            df.set_value(idx, 'STL', values[14])
            df.set_value(idx, 'BLK', values[15])
            df.set_value(idx, 'TOV', values[16])
            df.set_value(idx, 'PF', values[17])
            df.set_value(idx, 'PTS', values[18])
            if len(values) >= 20:   #some games don't have this last column
                df.set_value(idx, 'PM', values[19])
            idx += 1

    #Clean up data types
    df.Minutes = [int(x.split(':')[0])+float(x.split(':')[1])/60.0 if x!=0 else 0 for x in df.Minutes]
    df = df.convert_objects(convert_numeric=True)

    return df

def parse_nba_team_basic(table):
    df = pd.DataFrame()
    idx=0
    for row in table[0].findAll('tr'):
        if row.find('th').text == 'Team Totals':
            cols = row.findAll('td')

            values = [x.get_text() for x in cols]

            df.set_value(idx, 'Minutes', values[0])
            df.set_value(idx, 'FG', values[1])
            df.set_value(idx, 'FGA', values[2])
            df.set_value(idx, 'FGP', values[3])
            df.set_value(idx, '3P', values[4])
            df.set_value(idx, '3PA', values[5])
            df.set_value(idx, '3PP', values[6])
            df.set_value(idx, 'FT', values[7])
            df.set_value(idx, 'FTA', values[8])
            df.set_value(idx, 'FTP', values[9])
            df.set_value(idx, 'ORB', values[10])
            df.set_value(idx, 'DRB', values[11])
            df.set_value(idx, 'TRB', values[12])
            df.set_value(idx, 'AST', values[13])
            df.set_value(idx, 'STL', values[14])
            df.set_value(idx, 'BLK', values[15])
            df.set_value(idx, 'TOV', values[16])
            df.set_value(idx, 'PF', values[17])
            df.set_value(idx, 'PTS', values[18])
            if len(values) >= 20:   #some games don't have this last column
                df.set_value(idx, 'PM', values[19])


    #Clean up data types
#     df.Minutes = [int(x.split(':')[0])+float(x.split(':')[1])/60.0 if x!=0 else 0 for x in df.Minutes]
    df = df.convert_objects(convert_numeric=True)

    return df

# Returns a DF of cleaned up data values for advanced box score given table soup
def parse_nba_adv(table):
    df = pd.DataFrame()
    idx = 0
    for row in table[0].findAll('tr'):
        if row.find('a') is not None:
            df.set_value(idx, 'Player', str(row.find('a')).split('>')[1].split('<')[0])

            cols = row.findAll('td')
            if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
                values = [0]*20
            else:
                values = [x.get_text() for x in cols]

            df.set_value(idx, 'TSP', values[1])
            df.set_value(idx, 'EFGP', values[2])
            df.set_value(idx, '3PAR', values[3])
            df.set_value(idx, 'FTR', values[4])
            df.set_value(idx, 'ORBP', values[5])
            df.set_value(idx, 'DRBP', values[6])
            df.set_value(idx, 'TRBP', values[7])
            df.set_value(idx, 'ASTP', values[8])
            df.set_value(idx, 'STLP', values[9])
            df.set_value(idx, 'BLKP', values[10])
            df.set_value(idx, 'TOVP', values[11])
            df.set_value(idx, 'USGP', values[12])
            df.set_value(idx, 'ORTG', values[13])
            df.set_value(idx, 'DRTG', values[14])

            idx += 1

    #Clean up data types
    df = df.convert_objects(convert_numeric=True)

    return df

# Returns a DF of cleaned up data values for advanced box score given table soup
def parse_nba_team_adv(table):
    df = pd.DataFrame()
    idx = 0
    for row in table[0].findAll('tr'):
        if row.find('th').text == 'Team Totals':
            cols = row.findAll('td')

            values = [x.get_text() for x in cols]

            df.set_value(idx, 'TSP', values[1])
            df.set_value(idx, 'EFGP', values[2])
            df.set_value(idx, '3PAR', values[3])
            df.set_value(idx, 'FTR', values[4])
            df.set_value(idx, 'ORBP', values[5])
            df.set_value(idx, 'DRBP', values[6])
            df.set_value(idx, 'TRBP', values[7])
            df.set_value(idx, 'ASTP', values[8])
            df.set_value(idx, 'STLP', values[9])
            df.set_value(idx, 'BLKP', values[10])
            df.set_value(idx, 'TOVP', values[11])
            df.set_value(idx, 'USGP', values[12])
            df.set_value(idx, 'ORTG', values[13])
            df.set_value(idx, 'DRTG', values[14])

            idx += 1

    #Clean up data types
    df = df.convert_objects(convert_numeric=True)

    return df

# given a soup of the hitter's table, returns a df of hitter stats
def parse_hitter(table):
    # def parse_skaters(table):
    df = pd.DataFrame()
    idx = 0

    for row in table.findAll('tr'):
        if row.find('a') is not None:

            cols = row.findAll('td')
            values = [x.get_text() for x in cols]

            player = str(row.find('a')).split('>')[1].split('<')[0]
            df.set_value(idx, 'Player', player)

    #         if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
    #             values = [0]*16
    #         else:
    #             values = [x.get_text() for x in cols]

            df.set_value(idx, 'Runs', values[1])
            df.set_value(idx, 'Hits', values[2])
            df.set_value(idx, 'RBI', values[3])
            df.set_value(idx, 'BB', values[4])
            df.set_value(idx, 'Details', values[20])
            idx += 1
    for v in ['Runs', 'Hits', 'RBI', 'BB']:
        df[v] = pd.to_numeric(df[v])
        df[v] = df[v].fillna(0)

    return df


# given a dataframe of batter info with a details column, parses that details columns
def parse_hitter_details(batters):
    batters_details = batters.copy()
    col_list = ['2B', '3B', 'HR', 'SB', 'HBP']

    for col in col_list:
        batters_details[col] = 0

    for idx, row in batters.iterrows():
        details = row['Details']
        for col in col_list:
            if ('·'+col) in details:
                batters_details.set_value(idx, col, int(details.split(('·'+col))[0][-1:]))
            elif col in details:
                batters_details.set_value(idx, col, 1)
    return batters_details


# given a soup of the pitcher's table, returns a df of pitcher stats
def parse_pitcher(table):
    # def parse_skaters(table):
    df = pd.DataFrame()
    idx = 0

    for row in table.findAll('tr'):
        if row.find('a') is not None:

            cols = row.findAll('td')
            values = [x.get_text() for x in cols]

            player = str(row.find('a')).split('>')[1].split('<')[0]
            df.set_value(idx, 'Player', player)

    #         if cols[0].get_text() == 'Did Not Play' or cols[0].get_text() == 'Player Suspended' or cols[0].get_text() == 'Did Not Dress' or cols[0].get_text() == 'Not With Team':
    #             values = [0]*16
    #         else:
    #             values = [x.get_text() for x in cols]

            df.set_value(idx, 'IP', values[0])
            df.set_value(idx, 'ER', values[3])
            df.set_value(idx, 'SO', values[5])

            if idx == 0:
                df.set_value(idx, 'SP', 1)
            else:
                df.set_value(idx, 'SP', 0)

            idx += 1

    for var in ['IP', 'ER', 'SO', 'SP']:
        df[var] = pd.to_numeric(df[var])
        df[var] = df[var].fillna(0)

    return df


#Given soup of baseball ref game page, return winning and losing pitchers
def parse_pitcher_wins(soup):
    linescore = soup.findAll('table', {'class':'linescore'})[0]
    ls_text = linescore.findAll('tfoot')[0].findAll('td')[0]

    wp_fn = ls_text.getText().split('WP:\xa0')[1].split('\xa0')[0]
    wp_ln = ls_text.getText().split(wp_fn+'\xa0')[1].split('\xa0')[0]

    # lp_fn = ls_text.getText().split('LP:\xa0')[1].split('\xa0')[0]
    # lp_ln = ls_text.getText().split(lp_fn+'\xa0')[1].split('\xa0')[0]

    #returns winning pitcher
    return (wp_fn + ' ' + wp_ln)


#Updates the schedule up to stop_dt
def update_schedule(old_sched, season, sport, stop_dt):
    old_schedule = pd.read_csv(old_sched)
    last_dt = pd.to_datetime(np.max(old_schedule.Date))
    stop_dt = pd.to_datetime(stop_dt)
    if (stop_dt - last_dt) >= pd.Timedelta('1 days'):
        if sport == 'NHL':
            new_sched = get_nhl_schedule(season, stop_dt)
        elif sport == 'NBA':
            new_sched = get_nba_schedule(season, stop_dt)
        elif sport == 'MLB':
            new_sched = get_mlb_schedule(season, stop_dt)
        new_sched.to_csv(old_sched, index=False)
        return new_sched[new_sched['Date']>last_dt]
    else:
        return pd.DataFrame(columns=old_schedule.columns)


def get_schedule(season, sport, end_dt=None, today=False):
    if sport=='NBA':
        return get_nba_schedule(season, end_dt, today)
    elif sport=='NHL':
        return get_nhl_schedule(season, end_dt, today)
    elif sport=='MLB':
        return get_mlb_schedule(season, end_dt, today)
    else: return 'Error: No sport'


def get_mlb_schedule(season, end_dt=None, today=False):
    url = 'https://www.baseball-reference.com/leagues/MLB/%s-schedule.shtml' %(season)

    page = requests.get(url)
    tree = html.fromstring(page.content)

    soup = BeautifulSoup(page.content, "lxml")

    games = soup.find_all('p', {'class':"game"})

    #Creates Dataframe for holding table info
    data = pd.DataFrame()

    for r in range(0, len(games)):
        team_away = games[r].find_all('a')[0].getText()
        team_home = games[r].find_all('a')[1].getText()

        box = games[r].find_all('a')[2]['href']

        m = int(box.split('.shtml')[0][-5:-1][0:2])
        d = int(box.split('.shtml')[0][-5:-1][2:4])
        game_dt = pd.datetime(year=int(season), month = m, day = d)

        if end_dt is not None:
            if game_dt > end_dt:
                break

            # if game hasn't happened yet
        if 'previews' in box:
            score_away = None
            score_home = None
        else:
            score_away = games[r].getText().split('(')[1].split(')')[0]
            score_home = games[r].getText().split('(')[2].split(')')[0]

        data.set_value(r, 'Visitor Team', team_away)
        data.set_value(r, 'Home Team', team_home)
        data.set_value(r, 'Visitor Score', score_away)
        data.set_value(r, 'Home Score', score_home)
        data.set_value(r, 'Box Score', box)

        data.set_value(r, 'Date', game_dt)

    data['Date'] = pd.to_datetime(data['Date'])
    if today==True:
        data = data.loc[data['Date']==end_dt]

    return data

def get_nhl_schedule(season, end_dt=None, today=False):
    url = 'https://www.hockey-reference.com/leagues/NHL_%s_games.html' %(season)

    page = requests.get(url)
    tree = html.fromstring(page.content)

    soup = BeautifulSoup(page.content, "lxml")

    #All table rows of the table
    tr = soup.findAll('tr')

    #Creates Dataframe for holding table info
    data = pd.DataFrame()

    for r in range(0,len(tr)-1):
        for c in tr[r+1].findAll('td'):
            if (today==False) and('teams' in tr[r+1].find('a')['href']):
                break
            else:
                column = c.get('data-stat')
                data.set_value(r, 'Date', tr[r+1].find('th').getText())
                data.set_value(r, 'Box Score', tr[r+1].find('a')['href'])
                if column == 'visitor_team_name':
                    data.set_value(r, 'Visitor Team', c.getText())
                elif column == 'visitor_goals':
                    data.set_value(r, 'Visitor Goals', c.getText())
                elif column == 'home_team_name':
                    data.set_value(r, 'Home Team', c.getText())
                elif column == 'home_goals':
                    data.set_value(r, 'Home Goals', c.getText())
                elif column == 'overtimes':
                    data.set_value(r, 'Overtime', c.getText())
                elif column == 'game_duration':
                    data.set_value(r, 'Game Duration', c.getText())
                elif column == 'game_remarks':
                    data.set_value(r, 'Game Remarks', c.getText())

    data['Date'] = pd.to_datetime(data['Date'])

    if end_dt is not None:
        data = data.loc[data['Date']<=end_dt]
    if today == True:
        data = data.loc[data['Date']==end_dt]

    return data


#Returns a dataframe of the schedule of games given a season
def get_nba_schedule(season, end_dt, today=False, bubble_months=False):
    schedule = pd.DataFrame()
    
    if bubble_months:
        months_cons = ['october', 'november', 'december', 'january', 'february', 'march', 'july', 'august']
    else:
        months = ['october', 'november', 'december', 'january', 'february', 'march', 'april', 'may', 'june']
        #cuts down number of months to speed up script
        if end_dt.month >= 10:
            months_cons = months[0:end_dt.month-9]
        elif end_dt.month <= 6:
            months_cons = months[0:end_dt.month+3]
        else:
            print ('Error: todays date not in NBA season')

    for month in months_cons:
        url = 'http://www.basketball-reference.com/leagues/NBA_%s_games-%s.html' %(season, month)
        page = requests.get(url)
        tree = html.fromstring(page.content)
        soup = BeautifulSoup(page.content, "lxml")
        pause(5)

        #All table rows of the table
        tr = soup.findAll('tr')

        #Creates Dataframe for holding table info
        data = pd.DataFrame()

        #Iterates through rows 1 to n (because 0 just has headers)
        for r in range(0,len(tr)-1):
            #checks to see if the date is in the past
            # print (tr[r+1].find('th').getText())
            if tr[r+1].find('th').getText() != 'Playoffs':
                if today == False and pd.to_datetime(tr[r+1].find('th').getText()) <= end_dt:
                    #Gets the date column
                    data.set_value(r, 'Date', tr[r+1].find('th').getText())
                    #Gets other columns
                    for c in tr[r+1].findAll('td'):
                        column = c.get('data-stat')

                        if column == 'game_start_time':
                            data.set_value(r, 'Time', c.getText())
                        elif column == 'visitor_team_name':
                            data.set_value(r, 'Visitor Team', c.getText())
                        elif column == 'visitor_pts':
                            data.set_value(r, 'Visitor Points', c.getText())
                        elif column == 'home_team_name':
                            data.set_value(r, 'Home Team', c.getText())
                        elif column == 'home_pts':
                            data.set_value(r, 'Home Points', c.getText())
                        elif column == 'overtimes':
                            data.set_value(r, 'OT', c.getText())
                        elif column == 'game_remarks':
                            data.set_value(r, 'Notes', c.getText())
                        elif column == 'box_score_text':
                            data.set_value(r, 'Box Score', c.find('a')['href'])
                elif today == True and pd.to_datetime(tr[r+1].find('th').getText()) == end_dt:
                    #Gets the date column
                    data.set_value(r, 'Date', tr[r+1].find('th').getText())
                    #Gets other columns
                    for c in tr[r+1].findAll('td'):
                        column = c.get('data-stat')

                        if column == 'game_start_time':
                            data.set_value(r, 'Time', c.getText())
                        elif column == 'visitor_team_name':
                            data.set_value(r, 'Visitor Team', c.getText())
                        elif column == 'home_team_name':
                            data.set_value(r, 'Home Team', c.getText())
                    if len(data) == 0:
                        print ('Error: No games are being played today :(')
        schedule = schedule.append(data, ignore_index = True).reset_index(drop=True)

    #Filters out playoffs row
    schedule = schedule[schedule['Date']!='Playoffs']

    #Fixes link to boxscore
    if today==False:
        schedule['Box Score'] = ['www.basketball-reference.com' + x for x in schedule['Box Score']]

    #Adds datatypes
    schedule['Time'] = [str(x.split(':')[0]) + str(x.split(':')[1][0:2]) for x in schedule['Time']]
    schedule = schedule.convert_objects(convert_numeric=True)
    schedule['Date'] = pd.to_datetime(schedule['Date'])
    return schedule


# Returns abbreviated team name given the full name
def convert_nba_team(team):
    if 'Detroit' in team:
        return 'det'
    elif 'Cleveland' in team:
        return 'cle'
    elif 'Philadelphia' in team:
        return 'phi'
    elif 'Chicago' in team:
        return 'chi'
    elif 'Utah' in team:
        return 'uta'
    elif 'Denver' in team:
        return 'den'
    elif 'Minnesota' in team:
        return 'min'
    elif 'Charlotte' in team:
        return 'cho'
    elif 'Knicks' in team:
        return 'nyk'
    elif 'Spurs' in team:
        return 'sas'
    elif 'Washington' in team:
        return 'was'
    elif 'New Orleans' in team:
        return 'nop'
    elif 'Clippers' in team:
        return 'lac'
    elif 'Indiana' in team:
        return 'ind'
    elif 'Memphis' in team:
        return 'mem'
    elif 'Atlanta' in team:
        return 'atl'
    elif 'Toronto' in team:
        return 'tor'
    elif 'Miami' in team:
        return 'mia'
    elif 'Warriors' in team:
        return 'gsw'
    elif 'Nets' in team:
        return 'brk'
    elif 'Sacramento' in team:
        return 'sac'
    elif 'Phoenix' in team:
        return 'pho'
    elif 'Lakers' in team:
        return 'lal'
    elif 'Thunder' in team:
        return 'okc'
    elif 'Trail Blazers' in team:
        return 'por'
    elif 'Boston' in team:
        return 'bos'
    elif 'Houston' in team:
        return 'hou'
    elif 'Orlando' in team:
        return 'orl'
    elif 'Bucks' in team:
        return 'mil'
    elif 'Dallas' in team:
        return 'dal'


#Gets player position, height, and weight data
def get_nba_player_info(season=None):
    player_info = pd.DataFrame()
    alpha = 'abcdefghijklmnopqrstuvwxyz'

    for letter in alpha:
        url = 'http://www.basketball-reference.com/players/%s/' %letter
        page = requests.get(url)
        tree = html.fromstring(page.content)
        soup = BeautifulSoup(page.content, "lxml")
        pause(5)

        #All table rows of the table
        tr = soup.findAll('tr')

        #Creates Dataframe for holding table info
        data = pd.DataFrame()

        #Iterates through rows 1 to n (because 0 just has headers)
        for r in range(0,len(tr)-1):
            #Gets the date column
            data.set_value(r, 'Player', tr[r+1].find('th').getText())
            #Gets other columns
            for c in tr[r+1].findAll('td'):
                column = c.get('data-stat')

                if column == 'year_min':
                    data.set_value(r, 'year_min', c.getText())
                if column == 'year_max':
                    data.set_value(r, 'year_max', c.getText())
                if column == 'pos':
                    data.set_value(r, 'Position', c.getText())
                if column == 'height':
                    data.set_value(r, 'Height', c.getText())
                if column == 'weight':
                    data.set_value(r, 'Weight', c.getText())
        player_info = player_info.append(data, ignore_index = True).reset_index(drop=True)
    player_info['year_max'] = pd.to_numeric(player_info['year_max'])
    player_info['year_min'] = pd.to_numeric(player_info['year_min'])
    if season is not None:
        #player_info = player_info[(player_info['year_max']>=(season-1)) & (player_info['year_min']<=(season+1))]
        player_info = player_info[(player_info['year_max']>=(season-1))]
    return player_info

def pause(duration=2, min_pause=2):
    time.sleep(np.random.random()*min(duration, 2) + min_pause)
