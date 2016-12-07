import requests.auth
import praw
import configparser

cfg_file = configparser.ConfigParser()
cfg_file.read('url-unshortener.cfg')

APP_ID = cfg_file['reddit']['app_id']
APP_SECRET = cfg_file['reddit']['app_secret']
USER_AGENT = cfg_file['reddit']['user_agent']
REDDIT_ACCOUNT = cfg_file['reddit']['username']
REDDIT_PASSWD = cfg_file['reddit']['password']

# Request the token
client_auth = requests.auth.HTTPBasicAuth(APP_ID, APP_SECRET)
post_data = {"grant_type": "password", "username": REDDIT_ACCOUNT, "password": REDDIT_PASSWD}
headers = {"User-Agent": USER_AGENT}
response = requests.post("https://www.reddit.com/api/v1/access_token",
                         auth=client_auth, data=post_data, headers=headers)
access_token = response.json()['access_token']

# Use the token
headers = {"Authorization": "bearer " + access_token, "User-Agent": USER_AGENT}
response = requests.get("https://oauth.reddit.com/api/v1/me", headers=headers)

print(response.json())


# PRAW

reddit = praw.Reddit(user_agent=USER_AGENT, client_id=APP_ID, client_secret=APP_SECRET)

for submission in reddit.subreddit('funny').hot(limit=10):
    print(submission.title)



