import re
import praw
import configparser
import requests
import queue
import sys
import threading

import time

cfg_file = configparser.ConfigParser()
cfg_file.read('url-unshortener.cfg')

APP_ID = cfg_file['reddit']['app_id']
APP_SECRET = cfg_file['reddit']['app_secret']
USER_AGENT = cfg_file['reddit']['user_agent']
REDDIT_ACCOUNT = cfg_file['reddit']['username']
REDDIT_PASSWD = cfg_file['reddit']['password']

comments_to_process = queue.Queue()

# Start PRAW Reddit Session
print("Connecting...")
reddit = praw.Reddit(user_agent=USER_AGENT, client_id=APP_ID, client_secret=APP_SECRET, username=REDDIT_ACCOUNT,
                     password=REDDIT_PASSWD)
print("Connection successful. Reddit session started.\n")


# First pass
class CommentScanner:
    def __init__(self):
        self.max_commentlength = int(cfg_file['urlunshortener']['max_commentlength'])
        self.SCAN_SUBREDDIT = cfg_file.get('urlunshortener', 'scan_subreddit')
        self.subs_to_scan = reddit.subreddit(self.SCAN_SUBREDDIT)
        self.URLMATCH_PATTERN_STRING = cfg_file['urlunshortener']['url_regex_pattern_ignorehttps']
        self.regex_pattern = re.compile(self.URLMATCH_PATTERN_STRING)
        print("CommentScanner constructed.")

    def run(self):
        print("\nURL-Match RegEx used: \"", self.URLMATCH_PATTERN_STRING, "\"")
        print("Subreddits to scan: ", self.SCAN_SUBREDDIT)
        matchcounter = 0
        totalcounter = 0
        for comment in self.subs_to_scan.stream.comments():
            body = comment.body
            if len(body) < self.max_commentlength:
                match = self.regex_pattern.search(body)
                if match:
                    # print("\n\nMatch #", matchcounter, "   Total #", totalcounter,
                    #       "   URL: ", match.group(0))
                    comments_to_process.put(comment)
                    matchcounter += 1

            totalcounter += 1


# Second pass
class CommentFilter:
    def __init__(self):
        print("CommentProcessor constructed.")

    def run(self):
        while True:
            if comments_to_process.not_empty:
                comments_to_process.get()
                time.sleep(1)
                print("\nQueue size: ", comments_to_process.qsize())


def main():
    comment_filter = CommentFilter()
    comment_scanner = CommentScanner()

    process_thread = threading.Thread(target=comment_filter.run, args=())
    scan_thread = threading.Thread(target=comment_scanner.run, args=())

    process_thread.start()
    scan_thread.start()


def reveal_long_url(url):
    session = requests.Session()  # so connections are recycled
    try:
        resp = session.head(url, allow_redirects=True)
        if url == resp.url:
            raise Exception("URL is not shortened.")
        print(resp.url)
    except requests.exceptions.MissingSchema as e:
        print(str(e))
    except Exception as e:
        print("ERROR:", str(e))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted\n")
        sys.exit(0)
