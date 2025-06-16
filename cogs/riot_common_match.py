import discord
from discord import app_commands
from discord.ext import commands

import requests
from dotenv import load_dotenv
import os
import itertools
import time
import json
import sys
import asyncio
from utils.logger import logger
import urllib.parse

# json 파일 load
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "config.json")

if not os.path.isfile(config_path):
    sys.exit("'config.json' not found in project root! Please add it and try again.")
else:
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)

load_dotenv()
API_KEY = os.getenv("RIOT_API")

riot_match_config = config['riot_match']
BASE_URL = riot_match_config['api_url'] 
start_index = riot_match_config['start_index']        # Start index(Starting from latest match)
increase_index = riot_match_config['increase_index']   # Increase index(Get 80 matches at a time)
max_index = riot_match_config['max_index']            # Maximum number of matches to search
min_match_found = riot_match_config['min_match']
api_limit_interval = riot_match_config['api_limit_interval']

game_match_urls= {
    # "tft" : "tft/match/v1/matches/by-puuid",
    "lol" : "lol/match/v5/matches/by-puuid"
}

def get_puuid(player_tag):
    try:
        game_name, tag_line = player_tag.split('#')
    except ValueError:
        print("Invalid player tag format. Use 'game_name#tag_line'.")
        return None
    url = f"{BASE_URL}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    if response.status_code == 403:
        return {'error': 'API key is invalid or expired.'}
    if response.status_code == 404:
        return {'error': 'Player not found'}
    else:
        return {'error': 'Riot api request failed'}
    
def get_match_list(puuid, start=0, count=increase_index, game="lol"):
    url = f"{BASE_URL}/{game_match_urls[game]}/{puuid}/ids?start={start}&count={count}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print("Error:", response.status_code, response.json())
        return None

# def get_lol_match_info(match_id):
#     url = f"/lol/match/v5/matches/{match_id}"
#     headers = {"X-Riot-Token": API_KEY}
#     response = requests.get(url, headers=headers)
#     print(response)

#     if response.status_code == 200:
#         return response.json() #데이터 가공하기
#     else:
#         print("Error:", response.status_code, response.json())
#         raise ValueError(f"puuid 가져오기 {response.json()}")
    
class CommonMatch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="롤", description=f"두 플레이어의 최근 {max_index}경기 중 공통된 경기를 찾습니다.")
    async def lol_match(self, interaction: discord.Interaction, player1: str, player2: str):
        # 입력값 검증
        if player1 == player2:
            await interaction.response.send_message("동일 플레이어는 검색할 수 없습니다.")
            return
        
        # 플레이어의 puuid 결과 가져오기
        player1_puuid_result = get_puuid(player1)
        player2_puuid_result = get_puuid(player2)
        
        # puuid 검색 에러 처리
        if 'error' in player1_puuid_result:
            logger.error(f"riot_match || Player1 | {player1_puuid_result['error']}")
            await interaction.response.send_message(f"플레이어1 puuid 검색 에러 : {player1_puuid_result['error']}")
            return
        if 'error' in player2_puuid_result:
            logger.error(f"riot_match || Player2 | {player2_puuid_result['error']}")
            await interaction.response.send_message(f"플레이어2 puuid 검색 에러 : {player2_puuid_result['error']}")
            return

        player1_puuid = player1_puuid_result['puuid']
        player2_puuid = player2_puuid_result['puuid']

        if not player1_puuid:
            await interaction.response.send_message(f"플레이어 __{player1}__가 유효하지 않거나 찾을 수 없습니다.")
            return
        if not player2_puuid:
            await interaction.response.send_message(f"플레이어 __{player2}__가 유효하지 않거나 찾을 수 없습니다.")
            return
        
        player1_matches = []
        player2_matches = []
        current_index = 0
        await interaction.response.send_message(f"🔍 검색 중입니다...", ephemeral=True)

        while current_index < max_index:
            try:
                player1_matches.append(get_match_list(player1_puuid,current_index))
                player1_matches_flat = list(itertools.chain(*player1_matches))
                player2_matches.append(get_match_list(player2_puuid,current_index))
                player2_matches_flat = list(itertools.chain(*player2_matches))
                # 공통된 경기 배열
                common_values = list(set(player1_matches_flat) & set(player2_matches_flat))
            except ValueError as e:
                print(f"통신 오류 {e}")
                await interaction.followup.send("API 호출 중 오류가 발생했습니다.")
                return
            
            # 최소 검색 갯수
            if len(common_values) >= min_match_found:
                break

            current_index += increase_index
            await asyncio.sleep(api_limit_interval)

        # 공통된 경기가 최소값 이상 있으면 결과 출력 
        if common_values:
            # 플레이어 태그 분리
            player1_name, player1_tag = player1.split("#")
            player2_name, player2_tag = player2.split("#")

            # 공백 URI 인코딩
            player1_name_uri = urllib.parse.quote(player1_name, safe='')
            player2_name_uri = urllib.parse.quote(player2_name, safe='')

            # 검색 결과 정보 출력
            await interaction.followup.send(
                f"[**{player1}**](https://www.deeplol.gg/summoner/KR/{player1_name_uri}-{player1_tag})과 "
                f"[**{player2}**](https://www.deeplol.gg/summoner/KR/{player2_name_uri}-{player2_tag})의 최근 {max(len(player1_matches_flat), len(player2_matches_flat))} 경기중 공통된 경기 "
                f"{len(common_values)}개",
                suppress_embeds=True
            )
            match_info = ""
            count = 1

            # 경기 상세 정보 (deeplol 전적 검색 사이트 링크) 응답
            for match_id in common_values[:40]:
                try:
                    # 한 메세지에 경기 최대 20개로 제한하여 분리 전송
                    if count >= 20 and count % 20 == 0:
                        await interaction.followup.send(f"{match_info}", suppress_embeds=True)
                        match_info = ""
                    match_info += f"{count}. [{match_id}](https://www.deeplol.gg/summoner/KR/{player1_name_uri}-{player1_tag}/matches/{match_id})\n"
                    count += 1
                except ValueError as e:
                    print(f"Match info error {e}")
                    await interaction.followup.send(f"공통 경기 {len(common_values)}개 발견됨(경기 정보 불러오기 실패)")
                    return
            await interaction.followup.send(f"{match_info}", suppress_embeds=True)
        
        # 공통 경기 없으면
        else:
            await interaction.followup.send(f"최근 {current_index}경기 중 공통된 경기를 찾을 수 없습니다.")

async def setup(bot: commands.Bot):
    await bot.add_cog(CommonMatch(bot))