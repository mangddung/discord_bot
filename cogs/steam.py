import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
import pprint
import asyncio
import urllib.parse
from datetime import datetime, timezone
from utils import *
import json
import sys
import os
from dotenv import load_dotenv
load_dotenv()

EXCHANGERATES_API=os.getenv('EXCHANGERATES_API')

# JSON 파일 load
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "config.json")

if not os.path.isfile(config_path):
    sys.exit("'config.json' not found in project root! Please add it and try again.")
else:
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)

# 환율 정보 가져오기
def get_exchange_rate():
    res = requests.get(
        f'https://api.exchangeratesapi.io/v1/latest?access_key={EXCHANGERATES_API}'
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
    exchange_data = json.load(f)

# 저장 함수 (전체 config를 덮어씀)
def save_exchange_config():
    with open(EXCHANGE_FILE, "w", encoding="utf-8") as f:
        json.dump(exchange_data, f, indent=2, ensure_ascii=False)

#=====================================================================================================
# JSON 설정 가져오기
primary_region = config['steam']['primary_region']
secondary_region = config['steam']['secondary_region']

# 스팀 언어, 국가 코드 유효성 검증
sample_app_id = [570, 440, 730, 230410, 304930]
def test_steam_country_codes(region):
    verify = False
    for app_id in sample_app_id:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={region['country_code']}&l={primary_region['language']}"
        res = requests.get(url)
        if res.status_code != 200 or not res.json().get(str(app_id), {}).get("success", False):
            continue
        else:
            verify = True
    return verify

# JSON 설정 정보 검증
# 1. 스팀 API 요청으로 확인
primary_result = test_steam_country_codes(primary_region)
secondary_result = test_steam_country_codes(secondary_region)
if not primary_result:
    logger.warning(f"Steam || setting error | primary_region setting is invalid")
if not secondary_result:
    logger.warning(f"Steam || setting error | secondary_region setting is invalid")

# 2. exchange.json 으로 비교
if not primary_region['currency'] in exchange_data['rates']:
    logger.warning(f"Steam || setting error | invalid primary currency: {primary_region['currency']}")
if not secondary_region['currency'] in exchange_data['rates']:
    logger.warning(f"Steam || setting error | invalid secondary currency: {secondary_region['currency']}")

#=====================================================================================================
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
                embed = embed_form(message.author, game_info)
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
    # 기준 지역 게임 정보 조회
    url_base  = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={primary_region['country_code']}&l={primary_region['language']}"
    res_base  = requests.get(url_base)
    if res_base.status_code != 200:
        return
    if not res_base.json()[str(app_id)]['success']:
        return
    result_base = res_base.json()[str(app_id)]['data']

    # 데이터 추가
    game_info = {
        'app_id': app_id,
        'name': result_base['name'],
        'short_description': result_base['short_description'],
        'image': result_base['header_image'],
    }
    if result_base['is_free']:
        return game_info
    
    # 기준 가격 정보 저장
    price_base = result_base.get('price_overview')
    if price_base:
        if price_base.get('discount_percent', 0) != 0:
            game_info['base_initial_price'] = int(price_base['initial'] / 100)
            game_info['base_dc_percent'] = price_base['discount_percent']
        game_info['base_final_price_formatted'] = price_base.get('final_formatted')

    # 비교 지역 게임 정보 조회
    exchange = exchange_data['rates'][primary_region['currency']] / exchange_data['rates'][secondary_region['currency']]
    url_compare = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={secondary_region['country_code']}&l={primary_region['language']}"
    res_compare = requests.get(url_compare)
    if res_compare.status_code != 200:
        return game_info
    if not res_compare.json()[str(app_id)]['success']:
        return game_info
    result_compare = res_compare.json()[str(app_id)]['data']
    
    # 비교 가격 정보 저장
    price_compare = result_compare.get('price_overview')
    if price_compare:
        if price_compare.get('discount_percent', 0) != 0:
            game_info['compare_initial_price'] = int(price_compare['initial'] / 100)
            game_info['compare_dc_percent'] = price_compare['discount_percent']
        game_info['compare_final_price_formatted'] = price_compare.get('final_formatted')

        # 환율 가져오기
        base_currency_symbol = game_info['base_final_price_formatted'].split()[0]
        game_info['compare_price_in_base']=f"{base_currency_symbol} {int(result_compare['price_overview']['final']*exchange/100):,}"

    return game_info

def embed_form(author, game_info):
    safe_name = urllib.parse.quote(game_info['name'])
    embed = discord.Embed(
        title = game_info['name'],
        url = f"https://store.steampowered.com/app/{game_info['app_id']}/{safe_name}/",
        description=f"[Steam DB](https://steamdb.info/app/{game_info['app_id']})\n{game_info['short_description']}",
        color=discord.Color.default()
    )

    # author field
    embed.set_author(
        name=f"{author.display_name}",
        icon_url=author.display_avatar.url if author.display_avatar else None
    )

    embed.set_image(url=game_info['image'])
    if 'compare_final_price_formatted' not in game_info:
        embed.add_field(name="Price", value=f"Free", inline=False)
        return embed
    
    # 기준 가격 필드
    if game_info.get('base_dc_percent', 0) > 0:
        embed.add_field(name=f"Base Price({primary_region['country_code']})", value=f"~~{game_info['base_initial_price']:,}~~ (-{game_info['base_dc_percent']}%) -> {game_info['base_final_price_formatted']}", inline=False)
    else:
        embed.add_field(name=f"Base Price({primary_region['country_code']})", value=f"{game_info['base_final_price_formatted']}", inline=False)
    
    # 비교 가격 필드
    if game_info.get('compare_dc_percent', 0) > 0:
        embed.add_field(name=f"Compare Price({secondary_region['country_code']})", value=f"~~{game_info['compare_initial_price']:,}~~ (-{game_info['compare_dc_percent']}%) -> {game_info['compare_final_price_formatted']} ({game_info['compare_price_in_base']})", inline=False)
    else:
        embed.add_field(name=f"Compare Price({secondary_region['country_code']})", value=f"{game_info['compare_final_price_formatted']} ({game_info['compare_price_in_base']})", inline=False)

    return embed

# 환율 정보 config에 업데이트
def update_exchange_rate():
    global exchange_data
    data = get_exchange_rate()
    if data:
        exchange_data = data
        save_exchange_config()
        logger.info(f"Steam || Exchange rate updated: 1 {secondary_region['currency']} ≈ {exchange_data['rates'][primary_region['currency']]/exchange_data['rates'][secondary_region['currency']]:.2f} ({exchange_data['date']})")

# 업데이트 여부 확인
def update_exchange_if_stale():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if exchange_data["date"] != today:
        update_exchange_rate()

# 12시간마다 업데이트
async def exchange_rate_updater():
    while True:
        await asyncio.sleep(60 * 60 * 12)
        update_exchange_rate()