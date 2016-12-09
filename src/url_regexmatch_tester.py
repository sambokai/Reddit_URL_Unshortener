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
mismatchcounter = 0
totalcounter = 1
matchaverage = 0
mismatchaverage = 0
total_match = 0
total_mismatch = 0
time.clock()
matchroots = 0
matchsecondlevel = 0
matchthirdlevel = 0
begin = 0

# Start PRAW Reddit Session
print("Connecting...")
reddit = praw.Reddit(user_agent=USER_AGENT, client_id=APP_ID, client_secret=APP_SECRET, username=REDDIT_ACCOUNT,
                     password=REDDIT_PASSWD)
print("Connection successful. Reddit session started.\n")

try:
    MATCH_LIMIT = int(sys.argv[1])
except IndexError:
    MATCH_LIMIT = 30

print("URL-Match RegEx used: \"", URLMATCH_PATTERN_STRING, "\"")
print("Subreddits to scan: ", SCAN_SUBREDDIT)
print("Match limit: ", MATCH_LIMIT)


def endprogram():
    print("\n\n\n\nPROGRAM ENDED\n",
          "\nURL-Match RegEx used: ", URLMATCH_PATTERN_STRING,
          "\nNumber of matches: ", matchcounter,
          "\nThe average_match was: ", round(matchaverage * 1000.0, 4),
          "\nThe total_match was:   ", round(total_match * 1000.0, 4),
          "\nThe average_mismatch was: ", round(mismatchaverage * 1000.0, 4),
          "\nThe total_mismatch was:   ", round(total_mismatch * 1000.0, 4),
          "\nThe average was: ", round((mismatchaverage + matchaverage) / 2 * 1000.0, 4),
          "\nThe total was:   ", round((total_mismatch + total_match) * 1000.0, 4),
          "\nRealtime elapsed: ", round((time.time() - begin), 4), " seconds",
          "\nNumber of matches that were Top-Level: ", matchroots,
          "(", 100 * float(matchroots) / float(matchcounter), "%)"
                                                              "\nNumber of matches that were Second-Level: ",
          matchsecondlevel,
          "(", 100 * float(matchsecondlevel) / float(matchcounter), "%)"
                                                                    "\nNumber of matches that were "
                                                                    "Third-Level: ",
          matchthirdlevel,
          "(", 100 * float(matchthirdlevel) / float(matchcounter), "%)",
          "\nNumber of all other depths: ", (matchcounter - matchroots - matchsecondlevel - matchthirdlevel),
          "(", 100 * float(matchcounter - matchroots - matchsecondlevel - matchthirdlevel) /
          float(matchcounter), "%)",
          "\n\nEND\n")
    sys.exit(0)


def main():
    global matchroots, matchroots, matchcounter, total_match, matchaverage, matchsecondlevel
    global matchthirdlevel, totalcounter, mismatchaverage, mismatchcounter, total_mismatch, begin

    allsubs = reddit.subreddit(SCAN_SUBREDDIT)

    begin = time.time()
    for comment in allsubs.stream.comments():
        if len(comment.body) < MAX_COMMENTLENGTH:
            start = time.process_time()
            if regex_pattern.search(comment.body):
                thiselapsed = time.process_time() - start
                matchcounter += 1
                total_match += thiselapsed
                matchaverage = total_match / matchcounter

                if comment.is_root:
                    matchroots += 1
                else:
                    # cut off "t1_" from beginning, since reddit.comment() already adds "t1_" at the beginning
                    parent = reddit.comment(comment.parent_id[3:])
                    if parent.is_root:
                        matchsecondlevel += 1
                    else:
                        parentparent = reddit.comment(parent.parent_id[3:])
                        if parentparent.is_root:
                            matchthirdlevel += 1

                print("\n\nMatch #", matchcounter, "   Total #", totalcounter, "    Parent: ", comment.parent_id,
                      "   Length:  ", len(comment.body), "   URL: ", regex_pattern.search(comment.body),
                      "\nTime:    ", round(thiselapsed * 1000.0, 4),
                      "\n\nAverage: ", round(matchaverage * 1000.0, 4), "")

                if matchcounter == MATCH_LIMIT:
                    endprogram()

            else:
                thiselapsed = time.process_time() - start
                mismatchcounter += 1
                total_mismatch += thiselapsed
                mismatchaverage = total_mismatch / mismatchcounter

        totalcounter += 1


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted\n")
        endprogram()
