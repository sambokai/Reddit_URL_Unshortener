import configparser
import logging
import queue
import re
import threading
import time
from http import cookiejar

import praw
import requests
from bs4 import BeautifulSoup


# TODO: add "About" section in README.md (learning python, first python project, cs student, etc..)

# disallow cookies in all requests
class BlockAll(cookiejar.CookiePolicy):
    return_ok = set_ok = domain_return_ok = path_return_ok = lambda self, *args, **kwargs: False
    netscape = True
    rfc2965 = hide_cookie2 = False


req_session = requests.Session()
req_session.cookies.set_policy(BlockAll())

reddit = None
shorturl_services = None
reddit_account = None

# Queue of comments, populated by CommentScanner, to be filtered by CommentFilter
comments_to_filter = queue.Queue()
# Queue of comments, populated by CommentFilter, to be revealed and answered to by CommentRevealer
comments_to_reveal = queue.Queue()

# Config File
cfg_file = configparser.ConfigParser()
cfg_file.read('urlunshortener.cfg')

# Configure logger
defaultlevel = "INFO"
logfilename = str(time.strftime("%Y-%m-%d.%H-%M-%S") + '.urlunshortener.log')
logfilepath = str(cfg_file.get('logger', 'logfile_directory_path'))
logfilelevel = str(cfg_file.get('logger', 'eventlevel_threshold')).upper()

logger = logging.getLogger()

formatter = logging.Formatter('%(asctime)s: [%(levelname)s] %(message)s')

stderr_log_handler = logging.StreamHandler()
stderr_log_handler.setFormatter(formatter)
logger.addHandler(stderr_log_handler)

try:
    logger.setLevel(logfilelevel)
    logger.info(logfilelevel + " used as threshold level for logger.")
except ValueError as ve:
    logger.error(ve)
    logger.error("Error in configuration file. Invalid threshold level. Default value "
                 + defaultlevel + " will be used. Only messages above \"" + defaultlevel + "\"-level will be logged.")
    logger.setLevel(defaultlevel)

try:
    file_log_handler = logging.FileHandler(logfilepath + logfilename)
    file_log_handler.setFormatter(formatter)
    logger.addHandler(file_log_handler)
    logger.info("Logfile will be saved in: " + logfilepath + logfilename)
except FileNotFoundError as e:
    logger.error(e)
    logger.error("Will only log to console.")

logger.debug("Initialized logger")


def main():
    """ TESTLINK: http://ow.ly/h4p230754Gt """
    read_shorturlservices()
    logger.warning("Program started.")
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

        # Debug
        logger.debug("First-Pass RegEx: " + self.firstpass_pattern_string)
        logger.debug("Subreddits to scan: " + str(self.SCAN_SUBREDDIT))

    # in case pushshift stops working continue work on own implementation
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
        lastpage_timeout = 30  # timeout before restarting fetch, after having reached the most recent comment
        lastpage_url = None  # used to check if site has changed
        # fetch the latest 50 comments
        request = req_session.get('https://apiv2.pushshift.io/reddit/comment/search')
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
        logger.info("Start fetching comments...")
        # comment fetch loop
        while True:
            # request the comment-batch that comes after the initial batch
            request = req_session.get(next_page_url)
            json = request.json()
            comments = json["data"]
            meta = json["metadata"]
            # use the next_page url to determine wether there is new data
            # if "next_page" key doesnt exist in 'metadata", it means that we are on the most current site
            if 'next_page' in str(meta) and lastpage_url != (meta['next_page']):
                # process the current batch of comments
                for rawcomment in comments:
                    body = rawcomment['body']
                    # todo: implement a blacklist of users and subreddits in the check below.
                    # don't process comments of yourself AND don't process comments that are longer than max (cfg file)
                    is_me = rawcomment['author'].lower() == reddit_account.lower()
                    if not is_me and len(body) < self.max_commentlength:
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
                logger.debug("Reached latest page. Wait " + str(lastpage_timeout) + " seconds.")
                time.sleep(lastpage_timeout)
            logger.debug(str(lastpage_url))


# Second pass
class CommentFilter:
    def __init__(self):
        self.secondpass_pattern_string = cfg_file['urlunshortener']['secondpass_url_regex_pattern']
        self.secondpass_regex = re.compile(self.secondpass_pattern_string)

        # Debug
        logger.debug("Second-Pass RegEx: " + self.secondpass_pattern_string)

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
                match = self.secondpass_regex.search(comment['body'])
                if match:
                    url = completeurl(match.group(0))
                    if any(word.lower() in url.lower() for word in shorturl_services):
                        comments_to_reveal.put(comment)


# Third pass
class CommentRevealer:
    def __init__(self):
        self.thirdpass_pattern_string = cfg_file['urlunshortener']['thirdpass_url_regex_pattern']
        self.thirdpass_regex = re.compile(self.thirdpass_pattern_string)
        self.replyhead = cfg_file.get('replytexts', 'reply_header')
        self.replyfooter = cfg_file.get('replytexts', 'reply_footer')
        self.replylink = cfg_file.get('replytexts', 'reply_link')
        self.domain_blacklist = cfg_file.get('urlunshortener', 'blacklist_domains').replace(' ', '').split(',')

        self.wot_apikey = cfg_file.get('api', 'wot_apikey')
        # Debug
        logger.debug("Third-Pass RegEx: " + self.thirdpass_pattern_string)

    def run(self):  # TODO: only run this thread when comment is found & put in cmnts_to_reveal. dont run all the time
        while True:
            if comments_to_reveal.not_empty:
                comment = comments_to_reveal.get()
                # checking if own comment - safety net for debugging
                is_me = comment['author'].lower() == reddit_account.lower()
                if not is_me:
                    self.checkforreveal(comment)
                    time.sleep(2)
                else:
                    logger.debug("Ignoring own comment. @CommentRevealer Details: " + str(comment))

    def checkforreveal(self, comment):
        matches = self.thirdpass_regex.findall(comment['body'])
        if len(matches) > 0:  # i prefer the explicit check over the pythonic 'if not matches'.deal with it ;)
            logger.info("Found potential candidate. (Comment id: "
                        + str(comment['id']) + ") Comment details: " + str(comment))
            foundurls = []
            for match in matches:
                # check if it is a shorturl. and check if it contains a blacklisted domain.
                if any(word.lower() in match.lower() for word in shorturl_services) \
                        and not any(word.lower() in match.lower() for word in self.domain_blacklist):
                    shorturl = str(match)
                    try:
                        unshortened = unshorten_url(match)
                        link_entry = (shorturl, unshortened)
                        foundurls.append(link_entry)
                    except Exception as exception:
                        logging.exception("Error while trying to unshorten " + shorturl)

            if len(foundurls) > 0:
                # reply to comment
                try:
                    self.replytocomment(comment, foundurls)
                except Exception as ex:
                    logging.exception("Error while trying to reply to comment. Foundurls: " + str(foundurls) +
                                      "Comment:" + str(comment))
                # log
                logtext = "Found / replied to comment containing " + str(len(foundurls)) + " short-url(s):"
                for url in foundurls:
                    logtext += ("\nShort link: " + url[0] + " ; Unshortened link: " + url[1])
                logtext += ("\nComment details: " + str(comment) + "\n")
                logger.info(logtext)
            else:
                logger.info("False alarm. Comment did not contain any valid shorturls. (Comment id: " +
                            str(comment['id']) + ")")

    def replytocomment(self, comment, foundurls):
        replylinks = []
        self.replyhead = self.replyhead.format(urlcount=str(len(foundurls)))

        for index, link_entry in enumerate(foundurls, start=0):
            shorturl = str(link_entry[0])
            fullurl = str(link_entry[1])
            trust_rating = self.wot_trustcheck(fullurl)
            # wait before next 'web of trust' api request.
            time.sleep(3)
            replyline = self.replylink.format(linknumber=index + 1, shorturl=shorturl, fullurl=fullurl,
                                              trust=trust_rating[0], child=trust_rating[1])
            replylinks.append(replyline)
        replylinks = ''.join(replylinks)

        reply = self.replyhead + replylinks + self.replyfooter
        logger.info("Replying to comment " + comment['id'])
        comment_instance = reddit.comment(comment['id'])
        try:
            comment_instance.reply(reply)
        # fixme: handle errors like"praw.exceptions.APIException: RATELIMIT: 'try again in 9 min' on field 'ratelimit'"
        # if not allowed to post reply (i.e. ratelimit) wait some time and try again. up to N (maybe 2?) times.
        except Exception as exception:
            logger.error("Could not reply to comment " + str(comment['id']) + "\nError: " + str(exception))

    def wot_trustcheck(self, domain):
        api_link = "http://api.mywot.com/0.4/public_link_json2?hosts={domain}/&key={apikey}"
        api_link = api_link.format(domain=domain, apikey=self.wot_apikey)
        wot_response = req_session.get(api_link)
        wot_json = wot_response.json()
        # ratings with confidence levels below this value are marked as "uncertain" in the bot's reply
        confidence_threshold = 10
        trustworthiness = None
        child_safety = None
        # get only ONE key from json response (not elegant, but haven't found a better way of getting value of unknown
        # key from a json object
        try:
            for key, value in wot_json.items():
                # tuples of trustworthiness and childsafety rating.
                # element 0 is rating, element 1 is wot's confidence in that rating.
                trustworthiness = (value['0'][0], value['0'][1])
                child_safety = (value['4'][0], value['4'][1])
                if trustworthiness[1] > confidence_threshold:
                    trust = trustworthiness[0]
                else:
                    trust = "(Uncertain) " + str(trustworthiness[0])
                if child_safety[1] > confidence_threshold:
                    child = child_safety[0]
                else:
                    child = "(Uncertain) " + str(child_safety[0])
                rating = (trust, child)
                break
        except KeyError as ex:
            logger.exception("Error key while trust-checking " + str(domain))
            rating = ("No data", "No data")

        return rating


def read_shorturlservices():
    global shorturl_services

    shorturl_list_path = cfg_file.get('urlunshortener', 'shorturlserviceslist_path')

    # Read in list of shorturl-services as list-object.
    try:
        with open(shorturl_list_path) as f:
            shorturl_services = f.read().splitlines()
            for item in shorturl_services:
                item.lower()
    except FileNotFoundError as e:
        logger.error(e)
        logger.error("Please check services-list file or specified path in configuration file (.cfg) and restart "
                     "URLUnshortener.")
        raise SystemExit(0)


def connect_praw():
    global cfg_file, reddit
    app_id = cfg_file['reddit']['app_id']
    app_secret = cfg_file['reddit']['app_secret']
    user_agent = cfg_file['reddit']['user_agent']
    global reddit_account
    reddit_account = cfg_file['reddit']['username']
    reddit_passwd = cfg_file['reddit']['password']

    # Start PRAW Reddit Session
    logger.info("Connecting to Reddit...")
    reddit = praw.Reddit(user_agent=user_agent, client_id=app_id, client_secret=app_secret, username=reddit_account,
                         password=reddit_passwd)
    logger.info("Connection successful. Reddit session started.")


def completeurl(url):
    if url.endswith(" "):
        url = url[:-1]
    if (not url.startswith('http://')) and (not url.startswith('https://')):
        return 'http://' + url
    else:
        return url


def unshorten_url(url):
    url = completeurl(url)
    resolved_url = ""
    maxattempts = 3
    # try again in n seconds
    timeout = 5
    for attempt in range(maxattempts):
        try:
            resolved_url = resolve_shorturl(url)
            break
        except Exception as exception:
            logging.error("Attempt #" + str(attempt + 1) + " out of " + str(maxattempts) +
                          " max attempts failed. Error message: " + str(exception))
            if attempt + 1 == maxattempts:
                logging.error("All " + str(maxattempts) + " attempts have failed.")
                raise exception
            # wait [timeout] seconds before new attempt
            time.sleep(timeout)

    if url == resolved_url:
        raise Exception("URL is not shortened. URL: ", url)
    elif url.lower().startswith("http://") and resolved_url.lower().startswith("https://"):
        https_version = url[:4] + 's' + url[4:]
        if https_version == resolved_url:
            raise Exception("URL is not shortened. Target URL was https version of original link. URL: ", url)

    return resolved_url


def resolve_shorturl(url):
    url = completeurl(url)
    # desktop firefox user agent
    # headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X x.y; rv:10.0) Gecko/20100101 Firefox/10.0'}

    # internet explorer 11 user-agent string provides highest compatibility (i.e. with t.co, google drive)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko'}
    #  get response (header) and disallow automatic redirect-following, since we want to control that ourselves.
    response = req_session.head(url, headers=headers, allow_redirects=False)
    # if response code is a redirection (3xx)
    if 300 <= response.status_code <= 399:
        redirect_url = response.headers.get('Location')
        # Attempt to unshorten the redirect
        return resolve_shorturl(redirect_url)
    elif 200 <= response.status_code <= 299:
        # request the entire content (not just header) on "200" pages, in order to check for meta-refresh
        response = req_session.get(url, headers=headers, allow_redirects=False)
        soup = BeautifulSoup(response.content, "html.parser")
        meta_refresh = soup.find("meta", attrs={"http-equiv": "Refresh"})
        # dirty check for lower case "refresh tag" i.e. used by twitter (t.co)
        if not meta_refresh:
            meta_refresh = soup.find("meta", attrs={"http-equiv": "refresh"})
        # if html body contains a meta_refresh tag (which can be used to redirect to another url)
        if meta_refresh:
            wait, text = meta_refresh["content"].split(";")
            # if meta_refersh is indeed used to redirect and a url is provided
            textlow = text.strip().lower()[:4]
            if textlow == "url=":
                meta_redirect_url = text.strip()[4:]
                # attempt to unshorten the meta_refresh url
                return resolve_shorturl(meta_redirect_url)
        # fixme: check for javascript redirect using selenium
        else:
            return url
    else:
        raise Exception(str(
            response.status_code) + " HTTP Response. URL could not be unshortened. Is the link valid? (" + url + ")")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.error("KeyboardInterrupt")
        raise SystemExit(0)
