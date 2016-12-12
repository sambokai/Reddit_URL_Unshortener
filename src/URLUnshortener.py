import configparser
import queue
import re
import sys
import threading
import time

import praw
import requests

# TODO: add "About" section in README.md (learning python, first python project, cs student, etc..)

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
        self.firstpass_pattern_string = cfg_file['urlunshortener']['firstpass_url_regex_pattern']
        self.firstpass_regex = re.compile(self.firstpass_pattern_string)
        print("\nCommentScanner (Pass 1) constructed.")
        print("First-Pass RegEx: \"", self.firstpass_pattern_string, "\"")
        print("Subreddits to scan: ", self.SCAN_SUBREDDIT)

    def run(self):
        for comment in self.subs_to_scan.stream.comments():
            body = comment.body
            if len(body) < self.max_commentlength:
                match = self.firstpass_regex.search(body)
                if match:
                    # print("\n\nMatch #", matchcounter, "   Total #", totalcounter,
                    #       "   URL: ", match.group(0))
                    comments_to_process.put(comment)

    def run_pushshift(self):
        lastpage = None
        while True:
            request = requests.get('https://apiv2.pushshift.io/reddit/comment/search')
            json = request.json()
            comments = json["data"]
            meta = json["metadata"]

            if lastpage != meta['next_page']:
                for rawcomment in comments:
                    body = rawcomment['body']
                    if len(body) < self.max_commentlength:
                        match = self.firstpass_regex.search(body)
                        if match:
                            # print("\n\nMatch #", matchcounter, "   Total #", totalcounter,
                            #       "   URL: ", match.group(0))
                            comments_to_process.put(rawcomment)

                lastpage = meta['next_page']

            time.sleep(4)  # fixme: instead of every n seconds, refresh dynamically. (see comment below)
            # pushshift will implement after_id (reddit.com/r/pushshift/comments/5gawot)
            '''The closest thing you could do right now is to use the after parameter which works on the epoch time.
            You would want to look at the highest epoch time you got and subtract one and then make another call like
            this: https://apiv2.pushshift.io/reddit/comment/search/?after=1481537047&sort=asc (where the after value
            is whatever the second highest epoch time was that you received). You will get duplicate comments between
            calls like this, though -- but you are assured to get every comment. '''


# Second pass
class CommentFilter:
    def __init__(self):
        self.secondpass_pattern_string = cfg_file['urlunshortener']['secondpass_url_regex_pattern']
        self.secondpass_regex = re.compile(self.secondpass_pattern_string)
        print("\nCommentFilter (Pass 2) constructed.")

        print("Second-Pass RegEx: \"", self.secondpass_pattern_string, "\"")

    def run(self):
        while True:
            if comments_to_process.not_empty:
                comment = comments_to_process.get()
                print(comments_to_process.qsize())
                match = self.secondpass_regex.search(comment.body)
                if match:
                    url = completeurl(match.group(0))
                    print("\nQueue size: ", comments_to_process.qsize(), " URL: ",
                          url)

    def run_pushshift(self):
        while True:
            if comments_to_process.not_empty:
                comment = comments_to_process.get()
                match = self.secondpass_regex.search(comment['body'])
                if match:
                    url = completeurl(match.group(0))
                    print("\nQueue size: ", comments_to_process.qsize(), " URL: ",
                          url)


# Third pass
class CommentProcessor:
    def __init__(self):
        print("CommentProcessor (Pass 3) constructed")


def completeurl(url):
    if (not url.startswith('http://')) and (not url.startswith('https://')):
        return 'http://' + url
    else:
        return url


def main():
    comment_filter = CommentFilter()
    comment_scanner = CommentScanner()

    filter_thread = threading.Thread(target=comment_filter.run_pushshift, args=())
    scan_thread = threading.Thread(target=comment_scanner.run_pushshift, args=())

    filter_thread.start()
    scan_thread.start()


def reveal_long_url(url):
    session = requests.Session()  # so connections are recycled
    try:
        resp = session.head(url, allow_redirects=True)
        if url == resp.url:
            raise Exception("URL is not shortened.")
        return 'SUCCESS: ' + resp.url
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
