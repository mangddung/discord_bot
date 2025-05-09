import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get
import random
import copy

class Match(app_commands.Group):
    def __init__(self, bot: commands.Bot):
        super().__init__(name="경기", description="Match related commands")
        self.bot = bot
        self.team_voice_name = "#"
        self.participants = {}
        self.teams = {}
        self.result = {}

    @app_commands.command(name="생성", description="이전 경기 정보를 삭제하고 새로운 경기를 시작합니다.")
    async def create(self, interaction: discord.Interaction) -> None:
        self.participants = {}
        self.teams = {}
        self.result = {} 
        await interaction.response.send_message("경기 생성 완료")

    @app_commands.command(name="참가", description="자신 또는 다른 유저가 현재 진행중인 경기에 참가합니다.")
    async def participate(self, interaction: discord.Interaction, member: discord.Member=None) -> None:
        if member:
            if member.bot:
                await interaction.response.send_message("❌ 봇은 추가할 수 없습니다.")
                return
            target_info = [member.id, member.display_name]
        else:
            target_info = [interaction.user.id, interaction.user.display_name]
        if target_info[0] in self.participants:
            await interaction.response.send_message("❗ 이미 참가중인 유저입니다.")
            return
        self.participants[target_info[0]] = target_info[1]
        participants_list = "\n".join(name for id, name in self.participants.items())
        await interaction.response.send_message(f"✅ **{target_info[1]}**님을 추가했습니다.\n현재 참가자({len(self.participants)}명) : ```{participants_list}```")

    @app_commands.command(name="전체참가", description="명령어 사용자가 속한 보이스 채널 참여자들을 모두 경기에 참가시킵니다.")
    async def participate_all(self, interaction: discord.Interaction) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ 보이스 채널에 참가중이 아닙니다.")
            return
        members = interaction.user.voice.channel.members
        for member in members:
            if not member.bot:
                self.participants[member.id] = member.display_name
        participants_list = "\n".join(name for id, name in self.participants.items())
        await interaction.response.send_message(f"✅ 보이스 참가중인 **{len(members)}**명을 추가했습니다.\n현재 참가자({len(self.participants)}명) : ```{participants_list}```")

    @app_commands.command(name="제외", description="자신 또는 다른 유저를 현재 진행중인 경기에서 제외합니다.")
    async def remove(self, interaction: discord.Interaction, member: discord.Member=None) -> None:
        if member:
            target_info = [member.id, member.display_name]
        else:
            target_info = [interaction.user.id, interaction.user.display_name]
        if target_info[0] in self.participants:
            self.participants.pop(target_info[0])
            participants_list = "\n".join(name for id, name in self.participants.items())
            await interaction.response.send_message(f"✅ **{target_info[1]}**님을 제외했습니다.\n현재 참가자({len(self.participants)}명) : ```{participants_list}```") 
            return
        await interaction.response.send_message(f"❗ 해당 유저는 경기 참가중이 아닙니다.")    

    @app_commands.command(name="랜덤팀", description="참가자들을 자동으로 n개의 팀으로 나눕니다.")
    async def team_random(self, interaction: discord.Interaction, n: int) -> None:
        if n < 2:
            await interaction.response.send_message("❌ 팀 개수는 2개 이상이어야 합니다.", ephemeral=True)
            return
        if len(self.participants) < n:
            await interaction.response.send_message(f"❌ 참가자 수({len(self.participants)}명)가 팀 개수({n})보다 적습니다.", ephemeral=True)
            return
        
        shuffled_players = list(self.participants.keys())
        random.shuffle(shuffled_players)
        teams = {i + 1: [] for i in range(n)}
        for index, player in enumerate(shuffled_players):
            teams[(index % n) + 1].append(player)

        self.teams = copy.deepcopy(teams)
        team_message = "\n".join(
            f"**팀 {team_number}:** {', '.join(self.participants[player_id] for player_id in player_ids)}"
            for team_number, player_ids in self.teams.items()
        )
        await interaction.response.send_message(f"✅ **랜덤 팀 배정 결과**\n{team_message}")

    @app_commands.command(name="팀분배", description="각자 정해진 팀 보이스 채널로 이동합니다.")
    async def team_distribute(self, interaction: discord.Interaction) -> None:
        if not self.teams:
            await interaction.response.send_message("❌ 현재 정해진 팀이 없습니다.", ephemeral=True)
            return

        # 팀별 보이스 채널 이동
        for team_number, members in self.teams.items():  # 팀 정보 가져오기
            channel_name = f"{self.team_voice_name}{team_number}"
            channel = get(interaction.guild.voice_channels, name=channel_name) # 보이스 채널 가져오기
            if not channel: # 보이스 채널 없으면 생성
                try:
                    channel = await interaction.guild.create_voice_channel(channel_name)
                except Exception as e:
                    await interaction.response.send_message(f"❗ 보이스 채널 생성 중 오류 발생: {e}", ephemeral=True)
                    return
            for player_id in members:  # 유저 ID 리스트 가져오기
                member = interaction.guild.get_member(player_id)
                if not member:
                    continue 
                if not member.voice or not member.voice.channel:
                    continue
                try:
                    await member.move_to(channel)  # 채널 이동
                except Exception as e:
                    print(f"❗ {member.display_name} 이동 실패: {e}")  # 오류 출력
        
        await interaction.response.send_message(f"✅ 팀 분배 완료")

    @app_commands.command(name="팀확인", description="배정된 전체 팀을 확인합니다.")
    async def team_check(self, interaction: discord.Interaction) -> None:
        if not self.teams:
            await interaction.response.send_message(f"❗ 현재 배정된 팀이 없습니다.")
            return
        team_message = "\n".join(
        f"**팀 {team_number}:** {', '.join(self.participants[player_id] for player_id in player_ids)}"
        for team_number, player_ids in self.teams.items()
        )
        await interaction.response.send_message(f"✅ **현재 팀**\n{team_message}")

    @app_commands.command(name="팀이동", description="해당 유저를 n번 팀으로 이동시킵니다.")
    async def team_move(self, interaction: discord.Interaction, member: discord.Member, n: int) -> None:
        if member.id not in self.participants:
            await interaction.response.send_message(f"❗ 해당 유저는 경기 참가중이 아닙니다.")
            return
        if not self.teams:
            await interaction.response.send_message(f"❗ 현재 배정된 팀이 없습니다.")
            return
        if n not in self.teams:
            await interaction.response.send_message(f"❗ 이동시킬 팀 번호가 존재하지 않습니다.")
            return
        
        for team_number, members in self.teams.items():
            if member.id in members:
                members.remove(member.id)
        self.teams[n].append(member.id)
        await interaction.response.send_message(f"✅ **{member.display_name}** 님이 {n}번 팀으로 이동되었습니다.")

    @app_commands.command(name="종료", description="모든 보이스 채널 참가자들을 팀1의 보이스 채널로 이동합니다.")
    async def match_end(self, interaction: discord.Interaction) -> None:
        target_channel_number = 1
        for team_number in self.teams:
            channel_name = f"{self.team_voice_name}{team_number}"
            channel = get(interaction.guild.voice_channels, name=channel_name)
            if not channel and team_number == target_channel_number:
                target_channel_number += 1
                continue
            if not channel:
                continue
            if team_number == target_channel_number:
                continue
            target_channel_name = f"{self.team_voice_name}{target_channel_number}"
            target_channel = get(interaction.guild.voice_channels, name=target_channel_name)
            try:
                for member in channel.members:
                    await member.move_to(target_channel)
                await interaction.response.send_message(f"✅ 보이스 채널 이동 완료")
            except Exception as ex:
                print(f"Error: {ex}")

    # 결과입력
    # 팀 순서대로 순위를 입력합니다. 2팀인 경우 W, L 로 표시 가능

    # 결과삭제
    # 최근 입력한 경기 결과를 삭제합니다. 관리자 권환 확인 필수

    # 결과보기
    # 저장된 경기 결과를 보여줍니다.

    # @app_commands.command(name="", description="")
    # async def (self, interaction: discord.Interaction) -> None:
async def setup(bot: commands.Bot) -> None:
    bot.tree.add_command(Match(bot))
