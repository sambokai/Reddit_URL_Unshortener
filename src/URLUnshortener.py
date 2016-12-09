import re
import praw
import configparser
import time

import sys

cfg_file = configparser.ConfigParser()
cfg_file.read('url-unshortener.cfg')

MAX_COMMENTLENGTH = int(cfg_file['urlunshortener']['max_commentlength'])
SCAN_SUBREDDIT = cfg_file.get('urlunshortener', 'scan_subreddit')
URLMATCH_PATTERN_STRING = cfg_file['urlunshortener']['url_regex_pattern_ignorehttps']
regex_pattern = re.compile(URLMATCH_PATTERN_STRING)

APP_ID = cfg_file['reddit']['app_id']
APP_SECRET = cfg_file['reddit']['app_secret']
USER_AGENT = cfg_file['reddit']['user_agent']
REDDIT_ACCOUNT = cfg_file['reddit']['username']
REDDIT_PASSWD = cfg_file['reddit']['password']

matchcounter = 0
totalcounter = 1

# Start PRAW Reddit Session
print("Connecting...")
reddit = praw.Reddit(user_agent=USER_AGENT, client_id=APP_ID, client_secret=APP_SECRET, username=REDDIT_ACCOUNT,
                     password=REDDIT_PASSWD)
print("Connection successful. Reddit session started.\n")
allsubs = reddit.subreddit(SCAN_SUBREDDIT)

print("\nURL-Match RegEx used: \"", URLMATCH_PATTERN_STRING, "\"")
print("Subreddits to scan: ", SCAN_SUBREDDIT)


def main():
    global matchcounter, totalcounter
    for comment in allsubs.stream.comments():
        if len(comment.body) < MAX_COMMENTLENGTH:
            if regex_pattern.search(comment.body):
                matchcounter += 1
                print("\n\nMatch #", matchcounter, "   Total #", totalcounter, "    Parent: ", comment.parent_id,
                      "   Length:  ", len(comment.body), "   URL: ", regex_pattern.search(comment.body))

        totalcounter += 1


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted\n")
        sys.exit(0)
