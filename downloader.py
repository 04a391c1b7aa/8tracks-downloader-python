#Copyright Scott Opell 2012
#Licensed under the GPL license, see COPYING
import urllib2
import re
import pprint
import argparse
import os
import string
import sys
import subprocess
from urlparse import urlparse
#from ID3 import *
#import ID3
import mutagen.easyid3
import mutagen.id3
import mutagen.mp3
import mutagen.mp4
import time

try:
    import simplejson as json
except ImportError:
    import json

try:
     WindowsError
except NameError:
     WindowsError = None

VALID_CHARS = "-_.() %s%s" % (string.ascii_letters, string.digits)

class ConversionError(Exception):
    """Exception raised for error during conversion process
    Attributes:
        expr -- expression in which the error occurred
        msg  -- explanation of the error
    """
    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg


class Playlist:
    "Playlist container class for 8tracks playlists."
    def __init__(self, api, playlist_url):
        self.must_sleep = False
        self.current_song_no = 0
        self.playlist_url = playlist_url
        if len(api) != 40:
            raise Exception("Invalid api key %s" % api)
        else:
            self.api = api
        # initialize api and get playtoken
        api_url = 'http://8tracks.com/sets/new.json?api_key=' + api
        response = json.load(urllib2.urlopen(api_url))
        self.play_token = response.get('play_token')
        data = urllib2.urlopen(self.playlist_url).read()
        # seach through raw html for string mixes/#######/player, kind of messy, but best method currently
        matches = re.search(r'mixes/(\d+)/player', data)
        if matches.group(0) is not None:
            #this chooses the first match, its possible that 8tracks could change this later, but this works for now
            self.playlist_id = matches.group(1)
        else:
            raise Exception("invalid URL or 8tracks has updated to break compatibility, if the latter, contact me!")

        # get playlist "loader" basically the variable that will return song urls and will be iterated through
        playurl = urllib2.urlopen('http://8tracks.com/sets/'
                                  + self.play_token + '/play?mix_id='
                                  + self.playlist_id + '&format=jsonh&api_key=' + self.api)
        self.current_playlist_loader = json.load(playurl)

        # get playlist info
        info_url = urllib2.urlopen('http://8tracks.com/mixes/'+
                                   self.playlist_id +
                                   '.json?api_key='+ self.api)
        playlist_info = json.load(info_url)
        self.name = playlist_info['mix'].get('name', "No name")
        self.image_url = playlist_info['mix'].get('cover_urls').get('original')
        self.slug = playlist_info['mix'].get('slug', "No slug")
        global tracks_count
        tracks_count = int(playlist_info['mix'].get('tracks_count', "0"))
        print "Playlist has " + str(tracks_count) + " tracks."
        self.safe_name = filter(lambda c: c in VALID_CHARS, self.name)
        self.safe_slug = filter(lambda c: c in VALID_CHARS, self.slug)

    def __iter__(self):
        return self

    def next(self):
        if self.current_playlist_loader['set']['at_end']:
            raise StopIteration
        else:
            self.current_song_no += 1
            url = ('http://8tracks.com/sets/'+ self.play_token
                   + '/next?mix_id='+ self.playlist_id +
                     '&format=jsonh&api_key=' + self.api)
            try:
                playurl = urllib2.urlopen(url)
            except urllib2.HTTPError, err:
                print "Error! %s" % err
                if err.code == 403:
                    self.must_sleep = True
                    message = err.read()
                    print message
                    print "Access error! We probably need to wait for the cooldown timer to...cool down. Sleeping..."
                    time.sleep(210)
                    print "...attempting fetch again!"
                    playurl = urllib2.urlopen(url)
                else:
                    raise err

            track = self.current_playlist_loader['set'].get('track')
            self.current_playlist_loader = json.load(playurl)
            if self.must_sleep:
                # fixme: set to actual length of track!
                print "We have exceeded the max amount of fetches, sleeping..."
                time.sleep(210)
            return track

#stolen from http://stackoverflow.com/questions/273192/python-best-way-to-create-directory-if-it-doesnt-exist-for-file-write
def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

def norm_year(y):
    if y == '':
        return 0
    try:
        int(y)
        return y
    except:
        return 0

#takes a path to an m4a and returns the path to an mp3, will attempt to delete the m4a on successful conversion
def to_mp3(m4a_path):
    wav_path = m4a_path[:-4] + ".wav"
    mp3_path = m4a_path[:-4] + ".mp3"
    try:
      subprocess.call(["faad", '-q', '-o', wav_path, m4a_path])
      subprocess.call(["lame", '-h', '-b', '128', wav_path, mp3_path])
    except OSError:
      print "no such file or directory when converting"
      print m4a_path
      print "this error usually occurs when you don't have lame or faad"
    try:
        os.remove(wav_path)
    except WindowsError:
        print "windows error, error deleting wav"
    if os.path.isfile(mp3_path):
        try:
            os.remove(m4a_path)
        except WindowsError:
            print "Windows cannot delete the original m4a file, feel free to delete it manually after conversion"
        return mp3_path
    else:
        raise ConversionError(m4a_path, "mp3 file path does not exist for some reason")


pp = pprint.PrettyPrinter(indent=4)
parse = argparse.ArgumentParser(description = "Get valid playlist url/id and api key")
parse.add_argument('-u', '--playlist_url', required = True, help = "the URL of the playlist to be downloaded")
parse.add_argument('-a', '--API_key', required = True, help = "the URL of the playlist to be downloaded")
parse.add_argument('-d', '--save_directory', required = False, default = "./", help = "the directory where the files will be saved")
parse.add_argument('-mp3', required = False, action = "store_true", help = "if this is present then files will be output in mp3 format")

args = parse.parse_args()
mp3 = args.mp3
playlist = Playlist(args.API_key, args.playlist_url)

#get directory ready for some new tunes
directory = os.path.join(args.save_directory, playlist.safe_slug)

try:
    ensure_dir(os.path.join(directory, "test.txt"))
except:
    print "invalid path given, saving to current directory instead"
    directory = os.path.join(args.save_directory, playlist.safe_name)
    raise

m3u = []

image_stream = urllib2.urlopen(playlist.image_url)
real_image_url = urlparse(image_stream.geturl())
filetype = real_image_url.path[-4:]
f = open(os.path.join(directory, 'cover' + filetype),'wb')
f.write(image_stream.read())
f.close()

for song_number, song in enumerate(playlist, start=1):
    # song metadata/info
    # FIXME: error handling. What if these values are empty?
    curr_song_url = unicode(song['track_file_stream_url'])
    curr_artist = unicode(song['performer']).rstrip()
    curr_song_title = unicode(song['name']).rstrip().rstrip('.')
    curr_year = norm_year(song['year'])
    curr_album = unicode(song['release_name']).rstrip()
    # tracing through redirects
    try:
        urllib2.urlopen(curr_song_url)
    except urllib2.HTTPError:
        pp.pprint(playlist_loader)
        print "Song "+ str(song_number) + " not found, playlist includes reference to deleted song"
        continue

    actual_url = urllib2.urlopen(curr_song_url).geturl()
    parsed_url = urlparse(actual_url)
    # gets the filetype designated by the server
    filetype = parsed_url.path[len(parsed_url.path)-4:len(parsed_url.path)]

    if curr_year == 0:
        name_prototype = u"%(number)02d - %(artist)s - %(title)s" % {'number' : song_number,
                                                                              'artist' : curr_artist,
                                                                              'title'  : curr_song_title}
    else:
        name_prototype = u"%(number)02d - %(artist)s - %(title)s (%(year)d)" % {'number' : song_number,
                                                                              'artist' : curr_artist,
                                                                              'title'  : curr_song_title,
                                                                              'year'   : curr_year}

    # sanitize mp3_name and file_name
    file_name = filter(lambda c: c in VALID_CHARS, name_prototype + filetype)
    mp3_name = filter(lambda c: c in VALID_CHARS, name_prototype + ".mp3")

    file_path = os.path.join(directory, file_name)
    if os.access(file_path, os.F_OK):
        print "File number "+str(song_number)+" already exists!"
    elif os.path.isfile(os.path.join(directory, mp3_name)):
        print "File number "+str(song_number)+" already exists in mp3 format!"
        file_name = mp3_name
    else:
        print "Downloading " + str(song_number) + "/" + str(tracks_count) + ": " + file_name
        u = urllib2.urlopen(curr_song_url)
        f = open(file_path,'wb')
        f.write(u.read())
        f.close()
        if mp3 and (filetype != ".mp3"):
            try:
                to_mp3(file_path)
                file_name = mp3_name
                file_path = os.path.join(directory, file_name)
            except ConversionError:
                print "an error has occured converting track number " + str(song_number) + " to mp3 format, track will be left in m4a format"
        elif filetype == ".mp3":
            tags = mutagen.mp3.MP3(file_path, ID3=mutagen.easyid3.EasyID3)
        elif filetype == ".m4a":
            tags = mutagen.mp4.MP4(file_path)
        tags['title'] = curr_song_title
        tags['artist'] = curr_artist
        tags['album'] = curr_album
        tags['date'] = str(curr_year)
        tags.save(file_path)
        length = int(tags.info.length)
        for i in range(1, length + 1):
            print ("Pretending to play track: %d/%d seconds.          \r" % (i, length)),
            sys.stdout.flush()
            time.sleep(1)
        print ""

    m3u.append(file_name)

m3u_path = os.path.join(directory, playlist.safe_name + ".m3u")
m3u_file = open(m3u_path, 'w')
m3u_file.write("\n".join(m3u))
m3u_file.close()
print "Done, files can be found in "+directory
