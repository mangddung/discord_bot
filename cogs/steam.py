import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
import pprint
import asyncio
import urllib.parse
from datetime import datetime, timezone
from utils.logger import logger
import json
import sys
import os
from dotenv import load_dotenv
load_dotenv()

EXCHANGERATES_API=os.getenv('EXCHANGERATES_API')

# 환율 정보 가져오기
def get_exchange_rate():
    res = requests.get(
        f'https://api.exchangeratesapi.io/v1/latest?access_key={EXCHANGERATES_API}&symbols=RUB,KRW'
    )
    if res.status_code != 200:
        logger.error('Steam || failed to api request')
        return None
    data = res.json()
    if not data.get("success", False):
        logger.error('Steam || failed response from api')
        return None
    return data

# exchange.json 코드
# 현재 파일 기준으로 상위 디렉토리의 'db' 폴더 경로 설정
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_DIR = os.path.join(BASE_DIR, 'db')
EXCHANGE_FILE = os.path.join(DB_DIR, 'exchange.json')

# db 폴더 없으면 생성
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

# 초기 exchange.json 없으면 → API로 생성
if not os.path.isfile(EXCHANGE_FILE):
    logger.info("Steam || exchange.json 파일이 없어 API로부터 초기화합니다.")
    exchange_data = get_exchange_rate()
    if exchange_data:
        with open(EXCHANGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(exchange_data, f, indent=2, ensure_ascii=False)
        logger.info("Steam || exchange.json 생성 완료")
    else:
        logger.critical("❌ 환율 정보를 가져오지 못해 exchange.json을 초기화하지 못했습니다.")
        sys.exit(1)

# 파일 로드
with open(EXCHANGE_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 저장 함수 (전체 config를 덮어씀)
def save_exchange_config():
    with open(EXCHANGE_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
class Steam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # app_id 추출
        if message.content.startswith('https://store.steampowered.com/app'):
            match = re.search(r'/app/(\d+)', message.content)
            if not match:
                return
            app_id = match.group(1)
            try:
                game_info = get_game_info(app_id)
                embed = embed_form(game_info)
                await message.delete()
                await message.channel.send(embed=embed)
            except:
                return

async def setup(bot: commands.Bot) -> None:
    update_exchange_if_stale()
    asyncio.create_task(exchange_rate_updater())
    # bot.tree.add_command(SteamCommand(bot))
    await bot.add_cog(Steam(bot))

def get_game_info(app_id):
    # 한국 게임 정보 조회
    url_kr = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=KR&l=korean"
    res_kr = requests.get(url_kr)
    if res_kr.status_code != 200:
        return
    if not res_kr.json()[str(app_id)]['success']:
        return
    result_kr = res_kr.json()[str(app_id)]['data']

    # 데이터 추가
    game_info = {
        'app_id': app_id,
        'name': result_kr['name'],
        'short_description': result_kr['short_description'],
        'image': result_kr['header_image'],
    }
    if result_kr['is_free']:
        return game_info
    
    # KR 가격 정보
    if result_kr['price_overview']['discount_percent']!=0:
        game_info['kr_initial_price']=int(result_kr['price_overview']['initial']/100)
        game_info['kr_dc_percent']=result_kr['price_overview']['discount_percent']

    game_info['kr_final_price']=int(result_kr['price_overview']['final']/100)

    # 러시아 게임 정보 조회
    exchange = config['rates']['KRW'] / config['rates']['RUB']
    url_ru = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=RU&l=korean"
    res_ru = requests.get(url_ru)
    if res_ru.status_code != 200:
        return game_info
    if not res_ru.json()[str(app_id)]['success']:
        return game_info
    result_ru = res_ru.json()[str(app_id)]['data']
    
    # RU 가격 정보
    if result_ru['price_overview']['discount_percent']!=0:
        game_info['ru_initial_price']=int(result_ru['price_overview']['initial']/100)
        game_info['ru_dc_percent']=result_ru['price_overview']['discount_percent']

    game_info['ru_final_price']=int(result_ru['price_overview']['final']/100)
    game_info['ru_price_in_kr']=f"₩ {int(result_ru['price_overview']['final']*exchange/100):,}"

    return game_info

def embed_form(game_info):
    safe_name = urllib.parse.quote(game_info['name'])
    embed = discord.Embed(
        title = game_info['name'],
        url = f"https://store.steampowered.com/app/{game_info['app_id']}/{safe_name}/",
        description=game_info['short_description'],
        color=discord.Color.default()
    )
    embed.set_image(url=game_info['image'])
    if 'kr_final_price' not in game_info:
        embed.add_field(name="가격", value=f"무료", inline=False)
        return embed
    
    # 가격 정보 필드
    inline_TF = 'kr_final_price' in game_info and 'ru_final_price' in game_info
    # 한국 가격 필드
    if game_info.get('kr_dc_percent', 0) > 0:
        embed.add_field(name="한국 가격", value=f"~~{game_info['kr_initial_price']:,}~~ (-{game_info['kr_dc_percent']}%) -> {game_info['kr_final_price']:,}원", inline=inline_TF)
    else:
        embed.add_field(name="한국 가격", value=f"{game_info['kr_final_price']:,}원", inline=inline_TF)
    
    # 러시아 가격 필드
    if game_info.get('ru_dc_percent', 0) > 0:
        embed.add_field(name="러시아 가격", value=f"~~{game_info['ru_initial_price']:,}~~ (-{game_info['kr_dc_percent']}%) -> {game_info['ru_final_price']:,}루블({game_info['ru_price_in_kr']})", inline=inline_TF)
    else:
        embed.add_field(name="러시아 가격", value=f"{game_info['ru_final_price']:,}루블({game_info['ru_price_in_kr']})", inline=inline_TF)

    return embed

# 환율 정보 config에 업데이트
def update_exchange_rate():
    global config
    data = get_exchange_rate()
    if data:
        config = data
        save_exchange_config()
        logger.info(f"Steam || 환율 정보 갱신 완료: 1 RUB ≈ ₩{config['rates']['KRW']/config['rates']['RUB']:.2f} ({config['date']})")

# 업데이트 여부 확인
def update_exchange_if_stale():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if config["date"] != today:
        update_exchange_rate()

# 12시간마다 업데이트
async def exchange_rate_updater():
    while True:
        await asyncio.sleep(60 * 60 * 12)
        update_exchange_rate()