import discord
from discord import app_commands
from discord.ext import commands

import requests
from dotenv import load_dotenv
import os
import itertools
import time

load_dotenv()
API_KEY = os.getenv("RIOT_API")
BASE_URL = "https://asia.api.riotgames.com"

game_match_urls= {
    # "tft" : "tft/match/v1/matches/by-puuid",
    "lol" : "lol/match/v5/matches/by-puuid"
}

start = 0   # Start index(Starting from latest match)
increase= 50 # Increase index(Get 50 matches at a time)
max = 300 # Maximum number of matches to search

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
        return response.json()["puuid"]
    else:
        print("Error:", response.status_code, response.json())
        return None
    
def get_match_list(puuid, start=0, count=increase, game="lol"):
    url = f"{BASE_URL}/{game_match_urls[game]}/{puuid}/ids?start={start}&count={count}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print("Error:", response.status_code, response.json())
        return None

def get_lol_match_info(match_id):
    url = f"/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": API_KEY}
    response = requests.get(url, headers=headers)
    print(response)

    if response.status_code == 200:
        return response.json() #데이터 가공하기
    else:
        print("Error:", response.status_code, response.json())
        raise ValueError(f"puuid 가져오기 {response.json()}")
    
class CommonMatch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="롤", description=f"두 플레이어의 최근 {max}경기 중 공통된 경기를 찾습니다.")
    async def lol_match(self, interaction: discord.Interaction, player1: str, player2: str):
        # 입력값 검증
        if player1 == player2:
            await interaction.response.send_message("동일 플레이어는 검색할 수 없습니다.")
            return
        
        # 플레이어의 puuid 가져오기
        player1_puuid = get_puuid(player1)
        player2_puuid = get_puuid(player2)
        
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
        while True:
            try:
                player1_matches.append(get_match_list(player1_puuid,current_index))
                player1_matches_flat = list(itertools.chain(*player1_matches))
                player2_matches.append(get_match_list(player2_puuid,current_index))
                player2_matches_flat = list(itertools.chain(*player2_matches))
            except ValueError as e:
                print(f"통신 오류 {e}")
            
            if current_index >= max:
                await interaction.followup.send(f"검색 완료.  {max}경기 중 공통된 경기를 찾을 수 없습니다.")
                return

            # 공통된 경기 배열
            common_values = list(set(player1_matches_flat) & set(player2_matches_flat))

            # 공통된 경기가 있으면 결과 출력 
            if common_values:
                player1_name, player1_tag = player1.split("#")
                player2_name, player2_tag = player2.split("#")
                await interaction.followup.send(
                    f"[**{player1}**](https://www.deeplol.gg/summoner/KR/{player1_name}-{player1_tag})과 "
                    f"[**{player2}**](https://www.deeplol.gg/summoner/KR/{player2_name}-{player2_tag})의 최근 {current_index+increase} 경기중 공통된 경기 "
                    f"{len(common_values)}개",
                    suppress_embeds=True
                )
                match_info = ""
                count = 1
                for match_id in common_values:
                    try:
                        if count >= 20 and count % 20 == 0:
                            await interaction.followup.send(f"{match_info}", suppress_embeds=True)
                            match_info = ""
                        match_info += f"{count}. [{match_id}](https://www.deeplol.gg/summoner/KR/{player1_name}-{player1_tag}/matches/{match_id})\n"
                        count += 1
                    except ValueError as e:
                        print(f"Match info error {e}")
                        await interaction.followup.send(f"공통 경기 {len(common_values)}개 발견됨(경기 정보 불러오기 실패)")
                        return
                await interaction.followup.send(f"{match_info}", suppress_embeds=True)
                break
            # 공통된 경기가 없으면 인덱스 증가
            else:
                current_index+=increase
            time.sleep(3) #Control API rate imit

async def setup(bot: commands.Bot):
    await bot.add_cog(CommonMatch(bot))