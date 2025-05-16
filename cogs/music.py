import asyncio
import discord
from discord.ext import commands
import yt_dlp
from youtubesearchpython import VideosSearch, Video, Playlist
from utils.functions import *
from utils.logger import logger

from sqlalchemy import Column, Integer, String, desc
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
async def play_next_music(self, id, voice_client, guild_id):
    try:
        try:
            with get_db() as db:
                # 반복 재생 코드
                # repeat = bot_status_dict.get(int(guild_id), {}).get('repeat', repeat_dict[0]) # 반복 재생 설정 가져오기
                # if repeat == 'once':
                #     next_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
                # elif repeat == 'all':
                #     current_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
                #     last_queue = db.query(Queues).filter(Queues.guild_id == guild_id).order_by(desc(Queues.id)).first()
                #     if current_music and last_queue:
                #         current_music.id = last_queue.id + 1
                #         db.commit()
                #     next_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
                # elif repeat == 'off':
                #     queue_to_delete = db.query(Queues).filter(Queues.guild_id == guild_id).order_by(Queues.id).first()
                #     if queue_to_delete:
                #         guild_id = queue_to_delete.guild_id
                #         db.delete(queue_to_delete)  # 레코드 삭제
                #         db.commit()  # 삭제된 내용 저장
                #         next_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
                #     else:
                #         music_logger.warning(f"⚠️ No queue entry found for deletion | Guild: {guild_id}, Queue ID: {id}")
                queue_to_delete = db.query(Queues).filter(Queues.guild_id == guild_id).order_by(Queues.id).first()
                if queue_to_delete:
                    guild_id = queue_to_delete.guild_id
                    db.delete(queue_to_delete)  # 레코드 삭제
                    db.commit()  # 삭제된 내용 저장
                    next_music = db.query(Queues).filter(Queues.guild_id==guild_id).order_by(Queues.id).first()
        except Exception as ex:
            print(f"Error(play_next_music): {ex}")
            with get_db() as db:
                db.rollback()

        if next_music:
            # 요청자, 봇 채널 확인
            guild = self.bot.get_guild(int(next_music.guild_id))
            member = guild.get_member(int(next_music.member_id))
            member_voice = member.voice

            # 보이스 채널에 없으면 스킵
            if member_voice:
                member_voice_channel = member_voice.channel
            else:
                await play_next_music(self, next_music.id, voice_client, guild_id)
                return
            
            # 보이스 채널 다르면 같은 채널로 이동
            bot_voice_channel = guild.voice_client
            if bot_voice_channel and bot_voice_channel.is_connected():
                if bot_voice_channel.channel != member_voice_channel:
                    await bot_voice_channel.disconnect()
                    voice_client = await member_voice_channel.connect()
                else:
                    voice_client = bot_voice_channel

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(next_music.video_id, download=False)
                url2 = info['url']
            voice_client.play(
                discord.FFmpegPCMAudio(executable=ffmpeg_path, source=url2, **ffmpeg_options),
                after=lambda e: asyncio.run_coroutine_threadsafe(play_next_music(self, next_music.id, voice_client, guild_id),voice_client.loop)
            )
            logger.info(f"Music || 🎵 {next_music.video_title} 재생 시작 | Guild: {guild_id}, Music ID: {next_music.video_id}, Duration: {time_int_to_str(next_music.video_duration)}, Requester : {next_music.member_id}")
        else:
            logger.info(f"Music || 🎵 대기열이 비어있습니다. | Guild: {guild_id}")

        # 임베드 업데이트
        guild = self.bot.get_guild(int(guild_id))
        await update_panel_message(guild)

    except Exception as ex:
        print(f"Error(play_next_music): {ex}")
        with get_db() as db:
            db.rollback()

# 디스코드 봇 이벤트
#========================================================================================
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="전용채널")
    @commands.has_permissions(administrator=True)
    async def control_pannel(self, ctx):
        guild = ctx.guild
        search_channel = discord.utils.get(guild.text_channels, name="🎵노래봇-명령어")
        if search_channel:
            if guild.system_channel:
                await guild.system_channel.send("🎵노래봇-명령어 채널이 이미 존재합니다. 채널 삭제 후 봇을 다시 초대해주세요.")
                return
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send("🎵노래봇-명령어 채널이 이미 존재합니다. 채널 삭제 후 봇을 다시 초대해주세요.")
                    return
        else:
            created_channel = await guild.create_text_channel("🎵노래봇-명령어")

        embed, view = await create_panel_form(guild)
        created_message = await created_channel.send(embed=embed, view=view)
        with get_db() as db:
            try:
                guild_info = db.query(GuildMusicSettings).filter_by(guild_id=guild.id).first()
                if guild_info:
                    db.delete(guild_info)
                    db.commit()
                new_guild_info = GuildMusicSettings(guild_id=guild.id, channel_id=created_channel.id, message_id=created_message.id)
                db.add(new_guild_info)
                db.commit()
            except Exception:
                db.rollback()
                await created_channel.delete()
                await ctx.send("DB저장 중 오류가 발생했습니다. 다시 시도해주세요.")
                logger.error(f"Music || DB저장 중 오류 발생 | Guild: {guild.id}, Channel: {created_channel.id}")
            else:
                await ctx.send("전용채널이 생성되었습니다.")
                logger.info(f"Music || 전용채널 생성 성공 | Guild: {guild.id}, Channel: {created_channel.id}")
        
    @commands.command(name="패널재생성")
    @commands.has_permissions(administrator=True)
    async def recreate_panel(self, ctx):
        guild = ctx.guild
        with get_db() as db:
            try:
                guild_info = db.query(GuildMusicSettings).filter_by(guild_id=guild.id).first()
                if guild_info:
                    channel = self.bot.get_channel(guild_info.channel_id)
                    message = await channel.fetch_message(guild_info.message_id)
                    await message.delete()
                    embed, view = await create_panel_form(guild)
                    panel_message = await channel.send(embed=embed, view=view)
                    guild_info.message_id = panel_message.id
                    db.commit()
                    asyncio.create_task(delete_message_later(ctx.message, 1))
                    send_msg = await ctx.send("패널이 재생성되었습니다.")
                    asyncio.create_task(delete_message_later(send_msg, 3))
                    logger.info(f"Music || 패널 재생성 성공 | Guild: {guild.id}, Channel: {guild_info.channel_id}")
                else:
                    await ctx.send("패널이 생성되지 않았습니다. /전용채널 명령어를 사용하여 패널을 생성하세요.")
            except Exception:
                db.rollback()
                await ctx.send("패널 재생성 중 오류가 발생했습니다. 다시 시도해주세요.")
                logger.error(f"Music || 패널 재생성 중 오류 발생 | Guild: {guild.id}, Channel: {guild_info.channel_id}")

    # 봇 시작시 패널 재생성, 대기열 데이터 삭제
    @commands.Cog.listener()
    async def on_ready(self):
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
                        search_result = video_search_url(message.content)
                    else:
                        search_result = video_search(message.content)[0]
                except Exception as ex:
                    msg = await message.channel.send("검색 중 오류가 발생했습니다.")
                    asyncio.create_task(delete_message_later(msg, 3))
                    logger.error(f"Music || 노래 검색 오류 발생: {ex}")
                    return

                if not search_result:
                    return

                voice_channel = member.voice.channel
                voice_client = message.guild.voice_client
                if not voice_client:
                    voice_client = await member.voice.channel.connect()

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

            async def play_music():
                if guild_id not in guild_locks:
                    guild_locks[guild_id] = asyncio.Lock()
                lock = guild_locks[guild_id]
                async with lock:
                    if not voice_client.is_playing():
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = await asyncio.to_thread(ydl.extract_info, search_result['id'], False)
                            url2 = info['url']

                        def after_playing(e):
                            asyncio.run_coroutine_threadsafe(play_next_music(self, search_result['id'], voice_client, guild_id), self.bot.loop)

                        voice_client.play(
                            discord.FFmpegPCMAudio(executable=ffmpeg_path, source=url2, **ffmpeg_options),
                            after=after_playing
                        )
            # 노래 재생
            asyncio.create_task(play_music())
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

# 유튜브 검색 함수
# ========================================================================================
def video_search(query,search_count=1):
    # 비디오 검색
    try:
        search = VideosSearch(query, limit=search_count, region = 'KR')  # limit 검색 수
        results = search.result()
    except Exception as e:
        return None
    video_data = []
    for index in range(search_count):
        if results['result']:
            video_info = results['result'][index]
            video_title = video_info['title']
            video_id = video_info['id']
            #yt = Video.getInfo(video_info['link'])
            video_duration = video_info['duration']
            thumbnails_count = (len(video_info['thumbnails']))
            video_thumbnail = video_info['thumbnails'][thumbnails_count-1]['url']
            video_viewcount = view_eng_to_kr(video_info['viewCount']['short'])
            video_publishedtime = duration_eng_to_kr(video_info['publishedTime'])
            description_snippet = video_info['descriptionSnippet']
            channel_name = video_info['channel']['name']
            channel_profile = video_info['channel']['thumbnails'][0]['url']
            if not description_snippet:
                video_description = ''
            else:
                video_description = ''.join(item['text'] for item in description_snippet)
            video = {
                'title': video_title,
                'id': video_id,
                'duration': video_duration,
                'thumbnail' : video_thumbnail,
                'viewcount' : video_viewcount,
                'publishedtime' : video_publishedtime,
                'description' : video_description,
                'channel_name' : channel_name,
                'channel_profile' : channel_profile,
                #'age_restricted' : yt['isFamilySafe']
            }
            video_data.append(video)
        # 검색 결과 없으면 None 반환
        else:
            video_data = None
    return video_data

def video_search_url(url):
    if '&' in url:
        url = url.split('&')[0]
    if 'youtu.be' in url:
        url = url.split('?')[0]
    video_info = Video.getInfo(url)
    video_title = video_info['title']
    video_id = video_info['id']
    video_duration = time_int_to_str(int(video_info['duration']['secondsText']))
    thumbnails_count = (len(video_info['thumbnails']))
    video_thumbnail = video_info['thumbnails'][thumbnails_count-1]['url']
    video_viewcount = view_int_to_str(int(video_info['viewCount']['text']))
    video_publishedtime = publish_date_to_time(video_info['publishDate'])
    video_description = video_info['description']
    channel_name = video_info['channel']['name']
    #channel_profile = video_info['channel']['thumbnails'][0]['url']

    video = [{
        'title': video_title,
        'id': video_id,
        'duration': video_duration,
        'thumbnail' : video_thumbnail,
        'viewcount' : video_viewcount,
        'publishedtime' : video_publishedtime,
        'description' : video_description,
        'channel_name' : channel_name,
        #'channel_profile' : channel_profile,
    }]
    return video

# 임베드 함수
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
                member = guild.get_member(int(music['requester']))
                requester_nick = member.nick if member.nick else "Unknown"
                options.append(discord.SelectOption(label=music['title'], description=f"요청자: {requester_nick}, 영상 길이: {music['duration']}", value=str(idx)))
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
        voice_client.resume()
        await interaction.response.edit_message(content="곡을 재생합니다.", view=view)
        logger.info(f"Music || 재생 버튼 입력 | Guild: {guild.id}, User: {interaction.user.id}")

    # 중지 버튼
    async def pause_btn_callback(interaction):
        voice_client = guild.voice_client
        if voice_client:
            voice_client.pause()
            await interaction.response.edit_message(content="곡이 중지되었습니다.", view=view)
            logger.info(f"Music || 중지 버튼 입력 | Guild: {guild.id}, User: {interaction.user.id}")

    # 스킵 버튼
    async def skip_btn_callback(interaction):
        voice_client = guild.voice_client
        if voice_client:
            voice_client.stop()
            await interaction.response.edit_message(content="곡이 스킵되었습니다.", view=view)
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

def playing_embed_form(video_info):
    embed = discord.Embed(
        title = video_info['title'],
        url = video_info['url'],
        description="",
        color=discord.Color.default()
    )
    embed.set_image(url=video_info['thumbnail'])
    embed.add_field(name="요청자", value=f"<@{video_info['requester']}>", inline=True)
    embed.add_field(name="영상 길이", value=video_info['duration'], inline=True)

    return embed

async def update_panel_message(guild):
    try:
        with get_db() as db:
            db_guild_music_settings = db.query(GuildMusicSettings).filter(GuildMusicSettings.guild_id == guild.id).first()
            panel_channel = guild.get_channel(db_guild_music_settings.channel_id)
            panel_message = await panel_channel.fetch_message(db_guild_music_settings.message_id)
            play_queue = db.query(Queues).filter(Queues.guild_id == guild.id).order_by(Queues.id).limit(21).all()
            play_queue = [
                {
                    "title": q.video_title,
                    "duration": time_int_to_str(q.video_duration),
                    "requester": q.member_id,
                    "thumbnail": q.video_thumbnail,
                    "url": f"https://www.youtube.com/watch?v={q.video_id}"
                }
                for q in play_queue
            ]
            embed, view = await create_panel_form(guild,play_queue)
            await panel_message.edit(embed=embed, view=view)
    except Exception as ex:
        print(f"Error(update_panel_message): {ex}")
        with get_db() as db:
            db.rollback()
#========================================================================================
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))