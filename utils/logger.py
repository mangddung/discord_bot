import logging
from datetime import datetime
import pytz

# 한국 시간대 설정
tz = pytz.timezone("Asia/Seoul")

class KSTFormatter(logging.Formatter):
    def converter(self, timestamp):
        dt = datetime.fromtimestamp(timestamp, tz=tz)
        return dt

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        # yyyy-mm-dd-hh-mm-ss 형식
        s = dt.strftime("%Y-%m-%d %H:%M:%S") + f",{dt.microsecond // 1000:03d}"
        return s

# 로그 파일 & 콘솔 출력 핸들러 설정
file_handler = logging.FileHandler("discord_bot.log", encoding="utf-8")
stream_handler = logging.StreamHandler()

formatter = KSTFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# 로그 설정
logger = logging.getLogger("discord_bot")  # 로거 이름 설정
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# 로거를 다른 모듈에서 가져와 사용할 수 있도록 설정
__all__ = ["logger"]