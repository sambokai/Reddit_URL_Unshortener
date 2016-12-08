import re
import requests.auth
import praw
import configparser
from praw.models import MoreComments

cfg_file = configparser.ConfigParser()
cfg_file.read('url-unshortener.cfg')

MAX_COMMENTLENGTH = int(cfg_file['urlunshortener']['max_commentlength'])
URLMATCH_PATTERN_STRING = cfg_file['urlunshortener']['url_regex_pattern']
regex_pattern = re.compile(URLMATCH_PATTERN_STRING)

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

print(response.json(), "\n\n\n\n\n\n\n\n\n\n\n\n")

# Start PRAW Reddit Session
reddit = praw.Reddit(user_agent=USER_AGENT, client_id=APP_ID, client_secret=APP_SECRET, username=REDDIT_ACCOUNT,
                     password=REDDIT_PASSWD)

print(regex_pattern.search("testing www.bit.ly/qwodihqwoidh"))

counter = 1
allsubs = reddit.subreddit('all')
for comment in allsubs.stream.comments():
    if len(comment.body) < MAX_COMMENTLENGTH and regex_pattern.search(comment.body):
        print("TEST NUMBER ", counter, "\nComment Length: ", len(comment.body), "\n\n", comment.body,
              "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n")
        counter += 1
