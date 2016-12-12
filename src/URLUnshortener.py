import configparser
import queue
import re
import sys
import threading
import time

import praw
import requests

# TODO: add "About" section in README.md (learning python, first python project, cs student, etc..)

cfg_file = None
reddit = None
shorturl_services = None


# Queue of comments, populated by CommentScanner, to be filtered by CommentFilter
comments_to_filter = queue.Queue()
# Queue of comments, populated by CommentFilter, to be revealed and answered to by CommentRevealer
comments_to_reveal = queue.Queue()


def main():
    read_config()
    connect_praw()

    comment_filter = CommentFilter()
    comment_scanner = CommentScanner()
    comment_revealer = CommentRevealer()

    filter_thread = threading.Thread(target=comment_filter.run_pushshift, args=())
    scan_thread = threading.Thread(target=comment_scanner.run_pushshift, args=())
    reveal_thread = threading.Thread(target=comment_revealer.run, args=())

    filter_thread.start()
    scan_thread.start()
    reveal_thread.start()


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

    # in case pushshift stops working continue work on own implementation here
    '''
    def run(self):
        for comment in self.subs_to_scan.stream.comments():
            body = comment.body
            if len(body) < self.max_commentlength:
                match = self.firstpass_regex.search(body)
                if match:
                    # print("\n\nMatch #", matchcounter, "   Total #", totalcounter,
                    #       "   URL: ", match.group(0))
                    comments_to_filter.put(comment)
    '''

    def run_pushshift(self):
        initial_timeout = 10  # initial timeout before fetching the first batch
        lastpage_timeout = 20  # timeout before restarting fetch, after having reached the most recent comment
        lastpage_url = None  # used to check if site has changed
        # fetch the latest 50 comments
        request = requests.get('https://apiv2.pushshift.io/reddit/comment/search')
        json = request.json()
        comments = json["data"]

        # use the latest comment's id (#50 out of 50) to save the next url. pushshifts after_id paramater allows us to
        # continue after the specified id. that way no comments are skipped
        initial_page_url = "http://apiv2.pushshift.io/reddit/comment/search/?sort=asc&limit=50&after_id=" + \
                           str(comments[0]['id'])
        next_page_url = initial_page_url
        # fixme: dont skip first 50 comments; so instead of waiting, use the time to process the first 50 comments
        # wait before next api request, if we don't wait there will be no "metadata" element.
        time.sleep(initial_timeout)
        print("\nStart fetching comments...")
        # comment fetch loop
        while True:
            # request the comment-batch that comes after the initial batch
            request = requests.get(next_page_url)
            json = request.json()
            comments = json["data"]
            meta = json["metadata"]
            # use the next_page url to determine wether there is new data
            # if "next_page" key doesnt exist in 'metadata", it means that we are on the most current site
            if 'next_page' in str(meta) and lastpage_url != (meta['next_page']):
                # process the current batch of comments
                for rawcomment in comments:
                    body = rawcomment['body']
                    if len(body) < self.max_commentlength:
                        match = self.firstpass_regex.search(body)
                        if match:
                            # put relevant comments (containing urls) in queue for other thread to further process
                            comments_to_filter.put(rawcomment)
                # save on which page we are to check when new page arrives using the "next_page" link
                lastpage_url = meta['next_page']
                # use the "next_page" link to fetch the next batch of comments
                next_page_url = lastpage_url
                # wait before requesting the next batch
                time.sleep(1)
            else:
                print("\nReached latest page. Wait ", lastpage_timeout, " seconds.")
                time.sleep(lastpage_timeout)
            print(time.strftime('%X %x %Z'), lastpage_url)


# Second pass
class CommentFilter:
    def __init__(self):
        self.secondpass_pattern_string = cfg_file['urlunshortener']['secondpass_url_regex_pattern']
        self.secondpass_regex = re.compile(self.secondpass_pattern_string)
        print("\nCommentFilter (Pass 2) constructed.")

        print("Second-Pass RegEx: \"", self.secondpass_pattern_string, "\"")

    # in case pushshift stops working continue work on own implementation here
    '''
    def run(self):
        while True:
            if comments_to_filter.not_empty:
                comment = comments_to_filter.get()
                print(comments_to_filter.qsize())
                match = self.secondpass_regex.search(comment.body)
                if match:
                    url = completeurl(match.group(0))
                    print("\nQueue size: ", comments_to_filter.qsize(), " URL: ",
                          url)
    '''

    def run_pushshift(self):
        while True:
            if comments_to_filter.not_empty:
                comment = comments_to_filter.get()
                print(comment)
                match = self.secondpass_regex.search(comment['body'])
                if match:
                    url = completeurl(match.group(0))
                    if any(word in url for word in shorturl_services):
                        comments_to_reveal.put(comment)


# Third pass
class CommentRevealer:
    def __init__(self):
        print("\nCommentRevealer (Pass 3) constructed.")

    @staticmethod
    def run():  # TODO: only run this thread when comment is found & put into comments_to_reveal. dont run all the time
        while True:
            if comments_to_reveal.not_empty:
                comment = comments_to_reveal.get()
                print("shorturl: ", comment)


def read_config():
    global cfg_file, shorturl_services
    cfg_file = configparser.ConfigParser()
    cfg_file.read('url-unshortener.cfg')

    shorturl_list_path = cfg_file.get('urlunshortener', 'shorturlserviceslist_path')

    # Read in list of shorturl-services as list-object.
    try:
        with open(shorturl_list_path) as f:
            shorturl_services = f.read().splitlines()
    except FileNotFoundError as e:
        print(e)
        print("Please check services-list file or specified path in configuration file (.cfg) and restart "
              "URLUnshortener.")
        sys.exit(1)


def connect_praw():
    global cfg_file, reddit
    app_id = cfg_file['reddit']['app_id']
    app_secret = cfg_file['reddit']['app_secret']
    user_agent = cfg_file['reddit']['user_agent']
    reddit_account = cfg_file['reddit']['username']
    reddit_passwd = cfg_file['reddit']['password']

    # Start PRAW Reddit Session
    print("Connecting...")
    reddit = praw.Reddit(user_agent=user_agent, client_id=app_id, client_secret=app_secret, username=reddit_account,
                         password=reddit_passwd)
    print("Connection successful. Reddit session started.\n")


def completeurl(url):
    if (not url.startswith('http://')) and (not url.startswith('https://')):
        return 'http://' + url
    else:
        return url


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
