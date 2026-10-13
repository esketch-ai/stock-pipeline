import config
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

c = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
yt = build('youtube','v3',credentials=c,cache_discovery=False)
v = build('youtube','v3',credentials=c,cache_discovery=False).videos().list(part='snippet,status,contentDetails,statistics', id='WrOEhPqfjmA').execute()['items'][0]
print('Title:', v['snippet']['title'])
print('Privacy:', v['status']['privacyStatus'])
print('Duration:', v['contentDetails']['duration'])
print('Views:', v['statistics'].get('viewCount', 'N/A'))
print('Published:', v['snippet'].get('publishedAt'))
print('Tags:', ', '.join(v['snippet'].get('tags', [])))
print('URL: https://youtu.be/WrOEhPqfjmA')