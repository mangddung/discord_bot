from youtubesearchpython import VideosSearch, Video, Playlist
from .convert_utils import *

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

def playback_youtube_search(playback):
    isrc_results = video_search(playback['isrc'])
    if isrc_results:
        isrc_first = isrc_results[0]
        if is_same_song_by_duration(isrc_first['duration'], playback['duration_ms']):
            return isrc_first

    title_query = f"{playback['name']} {playback.get('artist', '')}"
    title_results = video_search(title_query)
    if title_results:
        for video in title_results:
            if is_same_song_by_duration(video['duration'], playback['duration_ms']):
                return video

        return title_results[0]

    return None

def is_same_song_by_duration(yt_duration_str, spotify_duration_ms, threshold_sec=3):
    try:
        minutes, seconds = map(int, yt_duration_str.split(':'))
        yt_seconds = minutes * 60 + seconds
        spotify_seconds = spotify_duration_ms // 1000
        return abs(yt_seconds - spotify_seconds) <= threshold_sec
    except:
        return False