import discord
from discord import app_commands
from discord.ext import commands
import random

class FunnyCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="난수뽑기", description="a부터 b 범위에서 n개의 난수를 뽑습니다.")
    async def random_nubmer(self, interaction: discord.Interaction, a: int, b: int, n: int=1):
        # 숫자 범위 확인하여 정정
        if a > b:
            a, b = b, a
        # 뽑는 숫자 n 개수 확인
        if n < 1 or n > (b-a+1):
            await interaction.response.send_message("n을 1 이상, 범위 보다 작은 숫자로 입력해주세요.")
            return
        # 랜덤 숫자 뽑기
        result = random.sample(range(a, b+1), n)
        result.sort()

        # 결과 전송
        result_str = ", ".join(map(str, result))
        await interaction.response.send_message(f"{a}~{b}사이 {n}개를 뽑았어요.\n추첨 결과: {result_str}")
        
    @app_commands.command(name="추첨1", description="목록 중에서 랜덤으로 1개를 뽑습니다.")
    async def random_choice1(self, interaction: discord.Interaction, list: str):
        # 문자열을 리스트로 변환
        choices_list = list.split(",")

        # 랜덤 1개 선택, 결과 전송
        result = random.choice(choices_list).strip()
        await interaction.response.send_message(f"리스트 : {list}\n추첨 결과: {result}")

    @app_commands.command(name="추첨2", description="실행자가 참가중인 보이스 채널 멤버 중에서 랜덤으로 1명을 뽑습니다.")
    async def random_choice2(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            await interaction.response.send_message("보이스 채널에 참가중이 아니에요. 참가 후 다시 시도해주세요.")

        # 채널 멤버 목록 가져오기
        voice_channel = interaction.user.voice.channel.members
        member_list = []
        for member in voice_channel:
            # 봇 확인
            if member.bot:
                continue
            display_name = member.nick if member.nick else member.global_name
            member_list.append(display_name)
            
        # 랜덤 1개 선택, 결과 전송
        result = random.choice(member_list).strip()
        await interaction.response.send_message(f"리스트 : {",".join(member_list)}\n추첨 결과: {result}")


async def setup(bot: commands.Bot):
    await bot.add_cog(FunnyCommand(bot))