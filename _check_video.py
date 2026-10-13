import config, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

c = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
yt = build('youtube','v3',credentials=c,cache_discovery=False)
v = build('youtube','v3',credentials=c,cache_discovery=False).videos().list(part='snippet,status', id='WrOEhPqfjmA').execute()['items'][0]

print('Title:', v['snippet']['title'])
print('Privacy:', v['status']['privacyStatus'])
print('Published:', v['snippet'].get('publishedAt'))
print('Description length:', len(v['snippet'].get('description','')))
print('Tags:', ', '.join(v['snippet'].get('tags',[])))