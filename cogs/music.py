import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
from youtubesearchpython import VideosSearch, Video, Playlist
from utils import *
import copy

from sqlalchemy import Column, Integer, String, Boolean, desc
from sqlalchemy.ext.declarative import declarative_base
from db import Base, get_db
import uuid

import os
from dotenv import load_dotenv
load_dotenv()

# DB 테이블 정의
# ========================================================================================
class GuildMusicSettings(Base):
    __tablename__ = 'guild_music_settings'

    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False)
    channel_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)

class Queues(Base):
    __tablename__ = 'queues'

    id = Column(Integer, nullable=False)
    guild_id = Column(Integer, nullable=False)
    member_id = Column(Integer, nullable=False)
    video_id = Column(String, nullable=False)
    video_title = Column(String, nullable=False)
    video_thumbnail = Column(String, nullable=False)
    video_duration = Column(Integer, nullable=False)
    is_spotify = Column(Boolean, nullable=False, default=False)
    isrc = Column(String, nullable=True)
    uuid = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

# 음악 재생 설정
#========================================================================================
ffmpeg_path = os.getenv('FFMPEG_PATH')  # FFmpeg 경로
ffmpeg_source = []
ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -bufsize 2M -threads 6'
    }
# yt-dlp로 유튜브 오디오 스트림을 가져옵니다.
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'extractaudio': True,
    'ratelimit': 5000000,
}
guild_locks = {}

# 음악 재생 관련 함수
#========================================================================================
async def play_next_music(self, voice_client, guild_id):
    try:
        with get_db() as db:
            first_queue_db = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
            if not first_queue_db:
                return
            
            # 멤버 정보 가져오기
            guild = self.bot.get_guild(int(guild_id))
            member = guild.get_member(int(first_queue_db.member_id))

            if member is None:
                return
            
            # 스포티파이 연동 재생 확인
            spotify_playback = None
            if first_queue_db.is_spotify:
                # 재생 완료 곡 삭제
                db.delete(first_queue_db)
                db.commit()
                
                # 스포티파이 활동 찾기
                spotify_activity = next(
                    (a for a in member.activities if isinstance(a, discord.Spotify)),
                    None
                )
                if not spotify_activity:
                    return
                
                # track_id로 현재곡 정보 조회
                spotify_playback = get_track_info(spotify_activity)
                if not spotify_playback:
                    return  
                
                # playback 정보로 유튜브 노래 검색
                search_result = playback_youtube_search(spotify_playback)
                if not search_result:
                    return
                
                # 새로운 곡 DB에 추가 ( 길드 설정에 따라 다르게 설정, 스포티파이 우선, 대기열 우선) 지금 코드는 대기열 우선
                next_queue = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
                if not next_queue:
                    try:
                        last_queue = db.query(Queues).filter(Queues.guild_id == guild_id).order_by(desc(Queues.id)).first()
                        if last_queue:
                            new_queue_id = last_queue.id+1
                        else:
                            new_queue_id = 1
                        new_queue = Queues(
                            id = new_queue_id,
                            guild_id=guild_id,
                            member_id=first_queue_db.member_id,
                            video_id=search_result['id'],
                            video_title=search_result['title'],
                            video_thumbnail=search_result['thumbnail'],
                            video_duration=time_str_to_int(search_result['duration']),
                            is_spotify = True,
                            isrc = spotify_playback['isrc']
                        )
                        db.add(new_queue)
                        db.commit()  # 레코드 저장
                    except Exception as ex:
                        db.rollback()
                        raise ValueError("스포티파이 대기열에 음악을 추가하는 중 오류가 발생했습니다.") from ex
                
                    next_music = new_queue
                else:
                    next_music = next_queue
            else:
                queue_to_delete = first_queue_db
                if queue_to_delete:
                    guild_id = queue_to_delete.guild_id
                    db.delete(queue_to_delete)  # 레코드 삭제
                    db.commit()  # 삭제된 내용 저장
                    next_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()

            if next_music:
                # 요청자, 봇 채널 확인
                member_voice = member.voice

                # 보이스 채널에 없으면 스킵
                if member_voice:
                    member_voice_channel = member_voice.channel
                else:
                    await play_next_music(self, voice_client, guild_id)
                    return
                
                # 보이스 채널 다르면 같은 채널로 이동
                bot_voice_channel = guild.voice_client
                if bot_voice_channel and bot_voice_channel.is_connected():
                    if bot_voice_channel.channel != member_voice_channel:
                        await bot_voice_channel.disconnect()
                        voice_client = await member_voice_channel.connect()
                    else:
                        voice_client = bot_voice_channel

                start_seconds = 0

                if next_music.is_spotify and spotify_playback is None:
                    # 다음 곡 스포티파이 활동 가져오기
                    spotify_activity = next(
                        (a for a in member.activities if isinstance(a, discord.Spotify)),
                        None
                    )
                    if not spotify_activity:
                        # 다음곡 요청한 유저가 스포티파이 재생중이 아니면 생략
                        db.delete(next_music)
                        db.commit()
                        return
                    spotify_playback = get_track_info(spotify_activity)
                    if not spotify_playback:
                        db.delete(next_music)
                        db.commit()
                        return
                    
                # 스포티파이 재생인 경우 ffmpeg 옵션 변경
                if next_music.is_spotify:
                    start_poition_result = get_spotify_start_position(spotify_playback)
                    if start_poition_result["should_skip"]:
                        db.delete(next_music)
                        db.commit()
                        return

                    start_seconds = start_poition_result["start_seconds"]

                    # -ss 옵션 추가
                    custom_ffmpeg_options = copy.deepcopy(ffmpeg_options)
                    custom_ffmpeg_options['before_options'] = f"-ss {start_seconds} " + custom_ffmpeg_options['before_options']
                else:
                    custom_ffmpeg_options = ffmpeg_options

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(next_music.video_id, download=False)
                    url2 = info['url']
                voice_client.play(
                    discord.FFmpegPCMAudio(executable=ffmpeg_path, source=url2, **custom_ffmpeg_options),
                    after=lambda e: asyncio.run_coroutine_threadsafe(play_next_music(self, voice_client, guild_id),voice_client.loop)
                )

            # 임베드 업데이트
            await update_panel_message(guild)

    except Exception as ex:
        print(f"Error(play_next_music): {ex}")
        with get_db() as db:
            db.rollback()

async def play_music(self, voice_client, guild_id, yt_id, interaction=None, spotify_playback=None):
    # 재생 프로세스(다운로드, 재생) 중복 요청 방지
    if guild_id not in guild_locks:
        guild_locks[guild_id] = asyncio.Lock()
    lock = guild_locks[guild_id]
    async with lock:
        if not voice_client.is_playing():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, yt_id, False)
                url2 = info['url']

            def after_playing(e):
                asyncio.run_coroutine_threadsafe(play_next_music(self, voice_client, guild_id), self.bot.loop)

            # 스포티파이 연동 재생인 경우
            if spotify_playback:
                result = get_spotify_start_position(spotify_playback)

                if result["should_skip"]:
                    if interaction:
                        await interaction.followup.send("해당 곡은 곧 끝나기 때문에 재생이 생략되었습니다. 잠시 후 다시 시도해주세요.")

                start_seconds = result["start_seconds"]

                # 기존 옵션을 복사해서 새로운 dict 생성
                custom_ffmpeg_options = copy.deepcopy(ffmpeg_options)
                custom_ffmpeg_options['before_options'] = f"-ss {start_seconds} " + custom_ffmpeg_options['before_options']
            
            else:
                start_seconds = 0
                custom_ffmpeg_options = copy.deepcopy(ffmpeg_options)
            voice_client.play(
                discord.FFmpegPCMAudio(executable=ffmpeg_path, source=url2, **custom_ffmpeg_options),
                after=after_playing
            )

# 스포티파이 주기적 동기화
async def sync_spotify(self):
    while True:
        for guild in self.bot.guilds:
            with get_db() as db:
                try:
                    # DB로 스포티파이 재생 확인
                    current_queue = db.query(Queues).filter(Queues.guild_id==guild.id).order_by(Queues.id).first()
                    if not current_queue:
                        continue
                    if not current_queue.is_spotify:
                        continue

                    # 보이스 클라이언트 가져오기
                    voice_client = guild.voice_client

                    # 멤버 가져오기
                    member = guild.get_member(current_queue.member_id)
                    if not member:
                        return
                    
                    # 스포티파이 활동 가져오기
                    spotify_activity = next(
                        (a for a in member.activities if isinstance(a, discord.Spotify)),
                        None
                    )
                    if not spotify_activity:
                        voice_client.stop()
                        await update_panel_message(guild)
                        return
                    
                    # track_id로 현재곡 정보 조회
                    spotify_playback = get_track_info(spotify_activity)
                    if not spotify_playback:
                        return  

                    # isrc 값으로 확인
                    if current_queue.isrc:
                        if spotify_playback['isrc'] == current_queue.isrc:
                            continue
                    # isrc없으면 유튜브 id로 비교
                    else:
                        # playback으로 검색
                        current_playback = playback_youtube_search(spotify_playback)
                        if not current_playback:
                            return
                        # 검색 결과 id 가 현재 곡과 같은 경우
                        if current_playback['id'] == current_queue.video_id:
                            continue

                    # 다르면 현재 곡으로 재생(스킵 기능으로)
                    voice_client.stop()
                except Exception as e:
                    print(f'sync_spotify error: {e}')
                finally:
                    db.close()

        await asyncio.sleep(5)
# 디스코드 봇 이벤트
#========================================================================================
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spotify_task = None

    @app_commands.command(
        name="전용채널", 
        description="노래봇 전용 채널을 생성합니다. 이름을 정하지 않으면 '🎵노래봇-명령어'로 생성됩니다."
    )
    @app_commands.default_permissions(administrator=True)
    async def control_pannel(self, interaction: discord.Interaction, channel_name: str = "🎵노래봇-명령어"):
        await interaction.response.defer()

        guild = interaction.guild
        search_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if search_channel:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(f"{channel_name} 채널이 이미 존재합니다. 채널 삭제 후 봇을 다시 초대해주세요.")
                    break
            return

        created_channel = await guild.create_text_channel(channel_name)
        embed, view = await create_panel_form(guild)
        created_message = await created_channel.send(embed=embed, view=view)

        with get_db() as db:
            try:
                guild_info = db.query(GuildMusicSettings).filter_by(guild_id=guild.id).first()
                if guild_info:
                    db.delete(guild_info)
                    db.commit()
                new_guild_setting = GuildMusicSettings(
                    guild_id=guild.id,
                    channel_id=created_channel.id,
                    message_id=created_message.id
                )
                db.add(new_guild_setting)
                db.commit()
                await interaction.followup.send("전용채널이 생성되었습니다.")
                logger.info(f"Music || 전용채널 생성 성공 | Guild: {guild.id}, Channel: {created_channel.id}")
            except Exception:
                db.rollback()
                await created_channel.delete()
                await interaction.followup.send("DB 저장 중 오류가 발생했습니다. 다시 시도해주세요.")
                logger.exception(f"Music || DB저장 중 오류 발생 | Guild: {guild.id}, Channel: {created_channel.id}")
        
    @app_commands.command(
        name="패널재생성",
        description="전용채널에 있는 패널을 재생성합니다. 오류가 발생했을 때 사용해주세요."
    )
    @app_commands.default_permissions(administrator=True)
    async def recreate_panel(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild = interaction.guild
        with get_db() as db:
            try:
                guild_info = db.query(GuildMusicSettings).filter_by(guild_id=guild.id).first()
                if not guild_info:
                    await interaction.followup.send("패널이 생성되지 않았습니다. `/전용채널` 명령어를 먼저 사용하세요.")
                    return

                channel = self.bot.get_channel(guild_info.channel_id)
                if channel is None:
                    await interaction.followup.send("기존 패널 채널을 찾을 수 없습니다.")
                    return

                try:
                    message = await channel.fetch_message(guild_info.message_id)
                    await message.delete()
                except discord.NotFound:
                    logger.warning(f"Music || 기존 메시지를 찾을 수 없음 | Guild: {guild.id}, Channel: {channel.id}")

                embed, view = await create_panel_form(guild)
                panel_message = await channel.send(embed=embed, view=view)

                guild_info.message_id = panel_message.id
                db.commit()

                await interaction.followup.send("패널이 재생성되었습니다.")
                logger.info(f"Music || 패널 재생성 성공 | Guild: {guild.id}, Channel: {channel.id}")

            except Exception:
                db.rollback()
                await interaction.followup.send("패널 재생성 중 오류가 발생했습니다. 다시 시도해주세요.")
                logger.exception(f"Music || 패널 재생성 중 오류 발생 | Guild: {guild.id}")

    @app_commands.command(
        name="스포티파이", 
        description="사용자의 스포티파이 활동을 기준으로 노래를 재생합니다."
    )
    @app_commands.default_permissions(administrator=True)
    async def spotify_play(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 보이스채널 참가 여부 확인
        member_voice = interaction.user.voice
        if not member_voice:
            await interaction.followup.send("보이스채널에 참가 후 사용해주세요.")
            return
        
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.followup.send("사용자의 활동을 찾을 수 없습니다. 잠시 후 다시 시도해주세요.")
            return
        
        # 스포티파이 활동 찾기
        spotify_activity = next(
            (a for a in member.activities if isinstance(a, discord.Spotify)),
            None
        )
        if not spotify_activity:
            await interaction.followup.send("스포티파이 활동이 없어요.\n스포티파이 계정을 디스코드에 연결 후 노래를 재생한 상태에서 시도해주세요.")
            return

        # track_id로 현재곡 정보 조회
        spotify_playback = get_track_info(spotify_activity)
        if not spotify_playback:
            await interaction.followup.send("현재곡 정보 검색 실패.")
            return  
        
        # playback 정보로 유튜브 노래 검색
        search_result = playback_youtube_search(spotify_playback)
        if not search_result:
            await interaction.followup.send("재생중인 스포티파이 곡으로 유튜브 영상 검색에 실패했습니다.")
            return
        
        try:
            with get_db() as db:
                # 대기열 추가 또는 재생
                last_queue = db.query(Queues).filter(Queues.guild_id == interaction.guild_id).order_by(desc(Queues.id)).first()
                if last_queue:
                    last_queue_id = last_queue.id
                    await interaction.followup.send(f"스포티파이 연동 재생을 대기열에 추가했습니다.")
                else:
                    last_queue_id = 0
                    await interaction.followup.send(f"스포티파이 연동 재생: {search_result['title']}을(를) 재생합니다.")
                
                member_voice_channel = member.voice.channel
                bot_voice_client = interaction.guild.voice_client

                if bot_voice_client and bot_voice_client.is_connected():
                    # 봇과 다른 채널이면 요청자 채널로 이동(대기열 비었을때)
                    if bot_voice_client.channel != member_voice_channel and not last_queue:
                        await bot_voice_client.disconnect()
                        voice_client = await member_voice_channel.connect()
                    else:
                        voice_client = bot_voice_client
                else:
                    voice_client = await member_voice_channel.connect()

                # 대기열 DB에 추가
                new_queue = Queues(
                    guild_id=interaction.guild_id,
                    member_id=member.id,
                    video_id=search_result['id'],
                    video_title=search_result['title'],
                    video_thumbnail=search_result['thumbnail'],
                    video_duration=time_str_to_int(search_result['duration']),
                    id=last_queue_id+1,
                    isrc = spotify_playback['isrc'],
                    is_spotify=True
                )
                db.add(new_queue)
                db.commit()

                # 패널 업데이트
                await update_panel_message(interaction.guild)

                # 노래 재생
                asyncio.create_task(play_music(self, voice_client, interaction.guild_id, search_result['id'], interaction, spotify_playback))
                logger.info(f"Music || 🎵 {search_result['title']} 재생 시작 | Guild: {interaction.guild_id}, Music Id: {search_result['id']}, Duration: {search_result['duration']}, Requester : {member.id}")
        except Exception as ex:
            with get_db() as db:
                db.rollback()
            await interaction.followup.send("오류가 발생했습니다. 다시 시도해주세요.")
            logger.error(f"Music || 스포티파이 연동 재생 오류 발생 | Guild: {interaction.guild_id}, Member: {interaction.user.id} Err: {ex}")

    # 봇 시작시 패널 재생성, 대기열 데이터 삭제
    @commands.Cog.listener()
    async def on_ready(self):

        if self.spotify_task is None or self.spotify_task.done():
            self.spotify_task = asyncio.create_task(sync_spotify(self))
            print("스포티파이 동기화 태스크 시작됨")
        with get_db() as db:
            try:
                # 대기열 데이터 삭제
                db.query(Queues).delete()
                db.commit()
                # 패널 재생성
                guild_settings = db.query(GuildMusicSettings).all()
                for setting in guild_settings:
                    guild = self.bot.get_guild(int(setting.guild_id))
                    if not guild:
                        continue
                    channel = guild.get_channel(int(setting.channel_id))
                    if not channel:
                        continue
                    message = await channel.fetch_message(int(setting.message_id))
                    if message:
                        await message.delete()
                    embed, view = await create_panel_form(guild)
                    created_message = await channel.send(embed=embed, view=view)
                    setting.message_id = created_message.id
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                logger.info("Music || 봇 시작 패널 재생성 및 대기열 데이터 삭제 완료")

    # 전용 채널 메세지 감지, 음악 재생
    @commands.Cog.listener()
    async def on_message(self, message):
        # 봇 메세지인 경우 무시
        if message.author.bot:
            return
        # 봇 명령어인 경우 무시
        prefix = await self.bot.get_prefix(message)
        if message.content.startswith(prefix[2]):
            return
        message_id = message.id
        channel_id = message.channel.id
        guild_id = message.guild.id
        member = message.author

        try:
            with get_db() as db:
                # DB에서 전용채널 설정 가져오기
                db_guild_setting = db.query(GuildMusicSettings).filter(GuildMusicSettings.guild_id == guild_id, GuildMusicSettings.channel_id == channel_id).first()
                if not db_guild_setting:
                    return

                # 사용자가 음성채널에 있는지 확인
                if not member or not member.voice:
                    msg = await message.channel.send("음성 채널에 참가해주세요.")
                    asyncio.create_task(delete_message_later(msg, 3))
                    return

                # 유튜브 주소 검색, 쿼리 검색 확인
                try:
                    if message.content.startswith("https://www.youtube.com/watch?v=") or message.content.startswith("https://youtu.be/"):
                        if "&list=" in message.content:
                            search_result = video_search_url(message.content.split('&list=', 1)[0])[0]
                        else:
                            search_result = video_search_url(message.content)[0]
                    else:
                        search_result = video_search(message.content)[0]
                except Exception as ex:
                    msg = await message.channel.send("검색 중 오류가 발생했습니다.")
                    asyncio.create_task(delete_message_later(msg, 3))
                    logger.error(f"Music || 노래 검색 오류 발생: {ex}")
                    return

                if not search_result:
                    return

                asyncio.create_task(delete_message_later(message, 3))

                # 대기열 추가 또는 재생
                last_queue = db.query(Queues).filter(Queues.guild_id == guild_id).order_by(desc(Queues.id)).first()
                if last_queue:
                    last_queue_id = last_queue.id
                    msg = await message.channel.send(f"{search_result['title']}을(를) 대기열에 추가했습니다.")
                else:
                    last_queue_id = 0
                    msg = await message.channel.send(f"{search_result['title']}을(를) 재생합니다.")
                asyncio.create_task(delete_message_later(msg, 3))
                
                member_voice_channel = member.voice.channel
                bot_voice_client = message.guild.voice_client

                if bot_voice_client and bot_voice_client.is_connected():
                    # 봇과 다른 채널이면 요청자 채널로 이동(대기열 비었을때)
                    if bot_voice_client.channel != member_voice_channel and not last_queue:
                        await bot_voice_client.disconnect()
                        voice_client = await member_voice_channel.connect()
                    else:
                        voice_client = bot_voice_client
                else:
                    voice_client = await member_voice_channel.connect()

                # 대기열 DB에 추가
                new_queue = Queues(
                    guild_id=guild_id,
                    member_id=member.id,
                    video_id=search_result['id'],
                    video_title=search_result['title'],
                    video_thumbnail=search_result['thumbnail'],
                    video_duration=time_str_to_int(search_result['duration']),
                    id=last_queue_id+1
                )
                db.add(new_queue)
                db.commit()

            # 패널 업데이트
            await update_panel_message(message.guild)

            # 노래 재생
            asyncio.create_task(play_music(self, voice_client, guild_id, search_result['id']))
            logger.info(f"Music || 🎵 {search_result['title']} 재생 시작 | Guild: {guild_id}, Music Id: {search_result['id']}, Duration: {search_result['duration']}, Requester : {member.id}")

        except Exception as ex:
            with get_db() as db:
                db.rollback()
            error_msg = await message.channel.send("오류가 발생했습니다. 다시 시도해주세요.")
            asyncio.create_task(delete_message_later(error_msg, 3))
            logger.error(f"Music || 노래 재생 오류 발생 | Guild: {guild_id}, Channel: {channel_id}, Query: {message.content}, Err: {ex}")

    # 음성 채널 아무도 없으면 연결 해제
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if self.bot.voice_clients:  # 봇이 음성 채널에 연결되어 있는지 확인
            voice_channel = self.bot.voice_clients[0].channel  # 봇이 연결된 음성 채널 객체 가져오기
            if voice_channel: # voice_channel이 None이 아닌지 확인 (봇이 연결이 끊어졌을 경우를 대비)
                members_in_channel = voice_channel.members  # 채널에 있는 멤버 목록 가져오기
                member_count = 0
                for member in members_in_channel:
                    if not member.bot:
                        member_count += 1
                if member_count == 0:
                    await self.bot.voice_clients[0].disconnect()
                    logger.info(f"Music || 음성 채널에 아무도 없어서 연결 해제 | Guild: {member.guild.id}, Channel: {voice_channel.id}")

#===============================================================================
panel_message_list = {
    'resume' : "▶ 재생",
    'pause' : "∥ 중지",
    'skip' : "▶| 스킵"
}

async def create_panel_form(guild,play_queue = []):
    view = discord.ui.View(timeout=None)
    # 버튼 생성
    play_btn = discord.ui.Button(label=panel_message_list['resume'], style=discord.ButtonStyle.secondary)
    pause_btn = discord.ui.Button(label=panel_message_list['pause'], style=discord.ButtonStyle.secondary)
    skip_btn = discord.ui.Button(label=panel_message_list['skip'], style=discord.ButtonStyle.secondary)
    if play_queue:
        if len(play_queue) > 1:
            options = []
            for idx, music in enumerate(play_queue[1:], start=1):
                title = music['title'] if not music['is_spotify'] else "스포티파이 연동 재생"
                options.append(discord.SelectOption(label=title, description=f"요청자: {music['author_name']}, 영상 길이: {music['duration']}", value=str(idx)))
            placeholder = f"다음 노래가 {len(play_queue)-1}개 있어요"
        else: 
            options = [discord.SelectOption(label="없어요."),]
            placeholder = "다음 노래가 없어요."
        embed = playing_embed_form(play_queue[0])
    else:
        embed = discord.Embed (title="재생중인 곡이 없어요.")
        options = [discord.SelectOption(label="없어요."),]
        placeholder = "다음 노래가 없어요."
    queue_dropdown = discord.ui.Select(placeholder=placeholder, options=options, min_values=1, max_values=1)

    # 재생 버튼
    async def play_btn_callback(interaction):
        voice_client = guild.voice_client
        if not voice_client:
            await interaction.response.send_message("음성 채널에 접속해 주세요.", ephemeral=True)
            return
        await interaction.response.edit_message(content="곡을 재생합니다.", view=view)
        voice_client.resume()
        logger.info(f"Music || 재생 버튼 입력 | Guild: {guild.id}, User: {interaction.user.id}")

    # 중지 버튼
    async def pause_btn_callback(interaction):
        voice_client = guild.voice_client
        if voice_client:
            await interaction.response.edit_message(content="곡이 중지되었습니다.", view=view)
            voice_client.pause()
            logger.info(f"Music || 중지 버튼 입력 | Guild: {guild.id}, User: {interaction.user.id}")

    # 스킵 버튼
    async def skip_btn_callback(interaction):
        voice_client = guild.voice_client
        if voice_client:
            await interaction.response.edit_message(content="곡이 스킵되었습니다.", view=view)
            voice_client.stop()
            logger.info(f"Music || 스킵 버튼 입력 | Guild: {guild.id}, User: {interaction.user.id}")

    #대기열 목록
    async def queue_dropdown_callback(interaction: discord.Interaction):
        voice_client = guild.voice_client
        if len(play_queue) > 1 and voice_client:
            # selected_option = int(queue_dropdown.values[0])
            # selected_music = play_queue.pop(selected_option)
            # play_queue.insert(1,selected_music)
            # voice_client.stop()
            # await interaction.response.send_message(f"{play_queue[1]['title']}을 재생합니다.",ephemeral=True)
            await interaction.response.send_message(f"아무 기능이 없어요. ",ephemeral=True)
        else:
            await interaction.response.send_message("아니 없어요",ephemeral=True)
    
    play_btn.callback = play_btn_callback  # 재생 버튼
    pause_btn.callback = pause_btn_callback  # 중지 버튼
    skip_btn.callback = skip_btn_callback  # 스킵 버튼
    queue_dropdown.callback = queue_dropdown_callback

    # 버튼을 포함한 뷰 생성
    view.add_item(queue_dropdown)
    view.add_item(play_btn)
    view.add_item(pause_btn)
    view.add_item(skip_btn)

    return embed,view

# 임베드 양식
def playing_embed_form(data):
    embed = discord.Embed(
        title = data['title'],
        url = f"https://www.youtube.com/watch?v={data['id']}",
        description="",
        color=discord.Color.default()
    )
    embed.set_image(url=data['thumbnail'])
    embed.set_author(name=f"{data['author_name']}", icon_url=data['author_avatar'])
    if data['is_spotify']:
        embed.set_footer(text="스포티파이 연동 재생", icon_url='https://storage.googleapis.com/pr-newsroom-wp/1/2023/05/Spotify_Primary_Logo_RGB_Green.png')
    embed.add_field(name="영상 길이", value=data['duration'], inline=True)

    return embed

# 노래 패널 업데이트
async def update_panel_message(guild):
    try:
        with get_db() as db:
            db_guild_music_settings = db.query(GuildMusicSettings).filter(GuildMusicSettings.guild_id == guild.id).first()
            panel_channel = guild.get_channel(db_guild_music_settings.channel_id)
            panel_message = await panel_channel.fetch_message(db_guild_music_settings.message_id)
            play_queue = db.query(Queues).filter(Queues.guild_id == guild.id).order_by(Queues.id).limit(21).all()
            queue_data = []
            for q in play_queue:

                member = guild.get_member(q.member_id)
                name_to_display = member.display_name if member.display_name else member.global_name
                member_avatar = str(member.display_avatar)
                if "?size" in member_avatar:
                    member_avatar = member_avatar.split("?")[0] + "?size=128"

                queue_data.append({
                    "title": q.video_title,
                    "duration": time_int_to_str(q.video_duration),
                    "author_name": name_to_display,
                    "author_avatar": member_avatar,
                    "thumbnail": q.video_thumbnail,
                    "id": q.video_id,
                    "is_spotify": q.is_spotify
                })
            embed, view = await create_panel_form(guild, queue_data)
            await panel_message.edit(embed=embed, view=view)
    except Exception as ex:
        print(f"Error(update_panel_message): {ex}")
        with get_db() as db:
            db.rollback()
#========================================================================================
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))