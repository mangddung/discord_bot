# Note: 'check_holiday' uses 'is_holiday' for Korean holidays only — replace or remove for other regions.

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, time, timedelta
from db import Base, get_db
from sqlalchemy import Column, String, Integer
import asyncio
import pytz
from holidayskr import is_holiday
from utils.logger import logger
import os
import json
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# config 파일 불러오기
# ========================================================================================
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "config.json")

if not os.path.isfile(config_path):
    sys.exit("'config.json' not found in project root! Please add it and try again.")
else:
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)

try:
    tz = ZoneInfo(config['timezone'])
    NOTICE_INTERVALS = config['sleep_mode']['notice_intervals']
except ZoneInfoNotFoundError:
    logger.error("Manage || Invalid timezone in config.json. Please input a valid IANA timezone (e.g. 'Asia/Seoul').")
    sys.exit(1)

# DB 테이블 정의
# ========================================================================================
class SleepMode(Base):
    __tablename__ = 'sleep_mode'
    user_id = Column(String, primary_key=True)
    username = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    weekdays = Column(Integer)
    weekends = Column(Integer)
    enabled = Column(Integer, default=0)

# ========================================================================================

# 취침모드 설정 모달 폼
class SleepModeModal(discord.ui.Modal, title="취침모드 설정"):
    weekdays_input = discord.ui.TextInput(label="요일 (평일, 휴일, 매일)", placeholder="평일, 휴일, 매일 중 하나 입력")
    start_time_input = discord.ui.TextInput(label="시작 시간 (HH:MM)", placeholder="예: 23:00")
    end_time_input = discord.ui.TextInput(label="종료 시간 (HH:MM)", placeholder="예: 06:00")

    # 제출시 DB처리
    async def on_submit(self, interaction: discord.Interaction):
        weekdays = self.weekdays_input.value
        start_time = self.start_time_input.value
        end_time = self.end_time_input.value

        member_name = interaction.user.nick if interaction.user.nick else interaction.user.name

        try:
            datetime.strptime(start_time, "%H:%M")
            datetime.strptime(end_time, "%H:%M")
        except ValueError:
            await interaction.response.send_message("시간 형식이 잘못되었습니다. HH:MM 형식으로 입력해주세요.", ephemeral=True)
            return

        with get_db() as db:
            db.query(SleepMode).filter(SleepMode.user_id == str(interaction.user.id)).delete()
            db.add(SleepMode(
                user_id=str(interaction.user.id),
                username=interaction.user.name,
                start_time=start_time,
                end_time=end_time,
                weekdays=1 if weekdays in ["평일", "매일"] else 0,
                weekends=1 if weekdays in ["휴일", "매일"] else 0,
                enabled=1
            ))
            db.commit()

        logger.info(f"SleepMode || {member_name}({interaction.user.id})님 취침모드 설정")
        await interaction.response.send_message(f"{weekdays}, {start_time}~{end_time}으로 설정되었습니다.", ephemeral=True)

class SleepModeCommand(app_commands.Group):
    def __init__(self, bot: commands.Bot):
        super().__init__(name="취침모드", description="취침 모드 관련 명령어")
        self.bot = bot

    @app_commands.command(name="설정", description="취침 모드를 설정합니다.")
    async def set_sleep_mode(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SleepModeModal())

    # DB 조회 및 메세지 전송
    @app_commands.command(name="켜기", description="취침 모드를 활성화합니다.")
    async def activate_sleep_mode(self, interaction: discord.Interaction):
        with get_db() as db:
            result = db.query(SleepMode).filter(SleepMode.user_id == str(interaction.user.id)).first()

            if not result:
                await interaction.response.send_message("❗ 취침 모드가 설정되지 않았습니다. `/취침모드 설정` 명령어를 사용해주세요.", ephemeral=True)
                return

            message = (f"{interaction.user.mention}, 현재 설정된 취침 모드 정보:\n"
                       f"시작 시간: {result.start_time}\n"
                       f"종료 시간: {result.end_time}\n"
                       f"주중 설정: {'활성화' if result.weekdays else '비활성화'}\n"
                       f"휴일 설정: {'활성화' if result.weekends else '비활성화'}")

            if not result.enabled:
                result.enabled = 1
                db.commit()
                message += "\n✅ 취침 모드가 활성화되었습니다."

        member_name = interaction.user.nick if interaction.user.nick else interaction.user.name
        logger.info(f"SleepMode || {member_name}({interaction.user.id})님 취침모드 활성화")
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="끄기", description="취침 모드를 비활성화합니다.")
    async def deactivate_sleep_mode(self, interaction: discord.Interaction):
        with get_db() as db:
            result = db.query(SleepMode).filter(SleepMode.user_id == str(interaction.user.id)).first()

            if not result:
                await interaction.response.send_message("❗ 취침모드 설정이 없습니다. `/취침모드 설정`으로 설정해주세요.", ephemeral=True)
                return

            if not result.enabled:
                await interaction.response.send_message("❗ 이미 비활성화 상태입니다.", ephemeral=True)
                return

            result.enabled = 0
            db.commit()

        member_name = interaction.user.nick if interaction.user.nick else interaction.user.name
        logger.info(f"SleepMode || {member_name}({interaction.user.id})님 취침모드 비활성화")
        await interaction.response.send_message("✅ 취침모드가 비활성화되었습니다.", ephemeral=True)

class SleepEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # check_sleep_mode 함수 루프 등록
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(check_sleep_mode(self))

    # 보이스 채널 변경시 추방 여부 확인
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        member_name = member.nick if member.nick else member.name
        if after.channel is None:
            return

        with get_db() as db:
            result = db.query(SleepMode).filter(
                SleepMode.user_id == str(member.id),
                SleepMode.enabled == 1
            ).first()

        if not result or not member.voice:
            return

        current_time = datetime.now(tz)
        start_dt = tz.localize(datetime.strptime(result.start_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day))
        end_dt = tz.localize(datetime.strptime(result.end_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day))

        if end_dt < start_dt:
            if time(0, 0) <= current_time.time() <= end_dt.time():
                start_dt -= timedelta(days=1)
            else:
                end_dt += timedelta(days=1)

        try:
            holiday = check_holiday(end_dt)
        except:
            logger.error(f"SleepMode || 날짜 형식 오류 발생 | {result}")
            return

        # 설정, 휴일 여부 비교하여 조건에 맞는 경우 스킵
        if (result.weekdays == holiday) and not (result.weekdays and result.weekends):
            return

        if start_dt <= current_time <= end_dt:
            await member.move_to(None)
            await member.send("현재 취침 시간입니다. 보이스 채널에 접속할 수 없습니다.")
            logger.info(f"SleepMode || {member_name}({member.id})님 취침모드 추방")

# 휴일인지 체크하는 함수(공휴일, 주말)
def check_holiday(dt):
    if not isinstance(dt, datetime):
        raise TypeError("올바른 날짜 형식이 아닙니다.")
    holiday = is_holiday(dt.strftime("%Y-%m-%d"))
    week = dt.weekday() >= 5
    return holiday or week

# 1분 간격으로 멤버가 추방 조건이 되는지 확인
async def check_sleep_mode(self):
    await self.bot.wait_until_ready()
    while not self.bot.is_closed():
        current_time = datetime.now(tz)

        with get_db() as db:
            results = db.query(SleepMode).filter(SleepMode.enabled == 1).all()

        for result in results:
            for guild in self.bot.guilds:
                member = guild.get_member(int(result.user_id))
                member_name = member.nick if member.nick else member.name
                if not member or not member.voice:
                    continue

                start_dt = tz.localize(datetime.strptime(result.start_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day))
                end_dt = tz.localize(datetime.strptime(result.end_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day))

                if end_dt < start_dt:
                    if time(0, 0) <= current_time.time() <= end_dt.time():
                        start_dt -= timedelta(days=1)
                    else:
                        end_dt += timedelta(days=1)

                holiday = check_holiday(end_dt)
                if (result.weekdays == holiday) and not (result.weekdays and result.weekends):
                    continue

                if start_dt <= current_time <= end_dt:
                    await member.move_to(None)
                    await member.send("현재 취침 시간입니다. 보이스 채널에 접속할 수 없습니다.")
                    logger.info(f"SleepMode || {member_name}({member.id})님 취침모드 추방")
                    continue

                for notice_interval in NOTICE_INTERVALS:
                    notice_time = start_dt - timedelta(minutes=notice_interval)
                    if notice_time <= current_time < (notice_time + timedelta(seconds=59)):
                        await member.send(f"곧 취침 시간입니다. {notice_interval}분 남았습니다.")
                        logger.info(f"SleepMode || {member_name}({member.id})님에게 {notice_interval}분전 메세지 전송")

        elapsed_time = (datetime.now(tz) - current_time).total_seconds()
        await asyncio.sleep(max(60 - elapsed_time, 0))

async def setup(bot: commands.Bot):
    bot.tree.add_command(SleepModeCommand(bot))
    await bot.add_cog(SleepEvent(bot))
