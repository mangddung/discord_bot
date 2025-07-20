from datetime import timedelta, datetime, timezone

time_list = [1, 60, 3600]
time_translate = {
    "year" : "년",
    "month" : "달",
    "week": "주",
    "day" : "일",
    "hour" : "시간",
    "minute" : "분",
    "second" : "초",
}
eng_unit_translate = {
    "K" : 1000,
    "M" : 1000000,
    "B" : 1000000000,
}
kr_unit_translate = {
    1000: "천",
    10000: "만", 
    100000000: "억", 
}
# 시간 문자열 -> 정수형 변환 함수
def time_str_to_int(time_str):
    time_int = list(map(int, time_str.split(':'))) # 영상 길이 정수형 배열로 변환
    time_int.reverse() # 배열 리버스
    time_seconds = 0 
    for index, element in enumerate(time_int):
        time_seconds += element * time_list[index]
    return time_seconds

# 시간 정수형 -> 문자열 변환 함수
def time_int_to_str(time_int):
    try:
        time_int = int(time_int)  # int 변환
    except (ValueError, TypeError):
        return "0:00"

    hours = time_int // 3600
    minutes = (time_int % 3600) // 60
    seconds = time_int % 60

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"  # HH:MM:SS
    else:
        return f"{minutes}:{seconds:02}"  # MM:SS
    
def duration_eng_to_kr(duration_eng):
    try:
        duration = duration_eng.split() # [숫자, 기간, ago] 생방 [Streamed, 숫자, 기간, ago]
        if duration[0]=='Streamed':
            duration[0] = '스트리밍 시간:'
            num_index = 2
        else:
            num_index = 1
        # 기간 뒤에 s 빼기
        if duration[num_index][-1]=='s':
            duration[num_index] = duration[num_index][:-1]
        # 기간 한글로 교체
        if duration[num_index] in time_translate:
            duration[num_index] = time_translate[duration[num_index]]
        return f"{"".join(duration[:-1])} 전"
    except:
        return duration_eng

def view_eng_to_kr(view_eng): # [7.3K, views]
    try:
        parts = view_eng.split()
        num_str = parts[0]
        # 조회수 숫자로 변환
        if num_str[-1] in eng_unit_translate:
            view_count = float(num_str[:-1]) * eng_unit_translate[num_str[-1]]
        else:
            view_count = num_str
        # 조회수 단위 한글로 변환
        kr_unit = ""
        kr_view = view_count
        for unit in kr_unit_translate:
            if view_count >= unit:
                kr_view = view_count / unit
                kr_unit = kr_unit_translate[unit]
                formatted = f"{kr_view:.1f}".rstrip("0").rstrip(".")
        return f"{formatted}{kr_unit}"
    except:
        return "0"

def view_int_to_str(view_int):
    if int(view_int) < 10000:
        return str(view_int)
    elif int(view_int) < 100000000:
        return f"{int(view_int)//10000}만"
    else:
        return f"{int(view_int)//100000000}억"
    
def video_id_from_url(url):
    video_id = url.split('/')[-1]
    if 'v=' in video_id:
        video_id = video_id.split('v=')[1]
    if '&' in video_id:
        video_id = video_id.split('&')[0]
    if '?' in video_id:
        video_id = video_id.split('?')[0]
    return video_id

def publish_date_to_time(date):
    publish_date = datetime.fromisoformat(date)
    published_time = datetime.now(timezone.utc) - publish_date

    # 총 경과 일수
    total_days = published_time.days

    # 년, 월, 일 계산
    years, remaining_days = divmod(total_days, 365)
    months, days = divmod(remaining_days, 30)

    if years > 0:
        return f"{years}년 전"
    elif months > 0:
        return f"{months}달 전"
    elif days > 0:
        return f"{days}일 전"
    
    # 시간이 하루 미만일 경우 (시, 분, 초 계산)
    total_seconds = published_time.total_seconds()
    if total_seconds >= 3600:  # 1시간 이상
        hours = int(total_seconds // 3600)
        return f"{hours}시간 전"
    elif total_seconds >= 60:  # 1분 이상
        minutes = int(total_seconds // 60)
        return f"{minutes}분 전"
    else:  # 1분 미만
        seconds = int(total_seconds)
        return f"{seconds}초 전"

def get_largest_time_unit(date):
    for key in time_translate.keys():
        if key in date:
            time_split = date.split(key)[0].strip()
            return f"{time_split.strip()}{time_translate[key]} 전"
    return date

