import spotipy, csv, time, re
import xml.etree.ElementTree as ET
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Dict

def library_to_csv(library_file):
    tree = ET.parse(library_file)
    root = tree.getroot()
    tracks = root.find('dict').find('dict')[1::2]

    with open('tracks.csv', 'w', newline='', encoding='utf-8') as tracks_file:
        tracks_writer = csv.writer(tracks_file)
        tracks_writer.writerow(['ID', 'Name', 'Artist', 'Album', 'Score', 'Length'])
        for track in tracks:
            track_dict = dict(zip([element.text for element in track[::2]], [element.text for element in track[1::2]]))
            if 'Loved' in track_dict and 'Rating Computed' not in track_dict and ('Comments' not in track_dict or track_dict['Comments'] == 'explicit') and 'Grouping' in track_dict:
                if track_dict['Grouping'] == 'Vocals' or track_dict['Grouping'] == 'Odd Vocals':
                    score = int(track_dict['Rating']) // 20
                    # if 'Loved' in track_dict:
                    #     score += 5
                    tracks_writer.writerow([track_dict['Track ID'], track_dict['Name'], track_dict.get('Artist', ''), track_dict.get('Album', ''), str(score), track_dict['Total Time']])
        tracks_writer.writerow([-1, '', '', '', '', ''])

library_to_csv('Library.xml')
# print('Converted library')

class Track:
    itunes_id: int
    name: str
    artist: str
    album: str
    score: int
    length: int
    spotify_id: str

    def __init__(self, tracks_row: List[str]):
        self.itunes_id = int(tracks_row[0])
        self.name = tracks_row[1]
        self.artist = tracks_row[2]
        self.album = tracks_row[3]
        self.score = int(tracks_row[4])
        self.length = int(tracks_row[5])
        self.spotify_id = ''


auth_manager = SpotifyClientCredentials('8fdaa3e8ba064b06835a866a5e9f282d', '580c6d8c97cb4222954f8a99d8411316')
sp = spotipy.Spotify(auth_manager=auth_manager)

rgx_name_ignore = re.compile(r'live|remaster|version|remix|acoustic', re.IGNORECASE)
rgx_name_brackets = re.compile(r'\[[^\]]+\]?')
rgx_name_parentheses = re.compile(r'\([^\)]+\)?')
rgx_name_feat = re.compile(r' ?\(?(?:feat\.|ft\.|featuring).+\)?', re.IGNORECASE)

succeeded = set()
failed = set()
spotify_ids: List[str] = []
to_add = ''
with open('tracks.csv', 'r', newline='') as tracks_file:
    tracks_reader = csv.reader(tracks_file)
    with open('tracks_features.csv', 'w', newline='') as tracks_features_file:
        tracks_features_writer = csv.writer(tracks_features_file)
        tracks_features_writer.writerow(['id','danceability','energy','key','loudness','mode','speechiness','acousticness','instrumentalness','liveness','valence','tempo','time_signature'])

        buffer: List[Track] = []

        index = 0
        for row in tracks_reader:
            if len(buffer) == 100 or row[0] == '-1':
                print()
                start = time.perf_counter()
                print('Getting features for buffer... ', end='')

                features = sp.audio_features([buf_track.spotify_id for buf_track in buffer])
                buffer_index = 0
                for track_features in features:
                    tracks_features_writer.writerow([buffer[buffer_index].itunes_id, track_features['danceability'], track_features['energy'], track_features['key'], track_features['loudness'], track_features['mode'], track_features['speechiness'], track_features['acousticness'], track_features['instrumentalness'], track_features['liveness'], track_features['valence'], track_features['tempo'], track_features['time_signature']])
                    buffer_index += 1
                buffer.clear()

                print(time.perf_counter() - start, 'ms')
                print()

            if row[0] != '-1' and row[0] != 'ID':
                index += 1
                track = Track(row)
                print('Searching for ' + track.name + '... ', end='')
                name = rgx_name_brackets.sub('', track.name).lower()

                search = sp.search(name, market='US')
                if len(search['tracks']['items']) == 0:
                    name = name.replace('&', 'and')
                    search = sp.search(name, market='US')

                if len(search['tracks']['items']) == 0 or int(search['tracks']['total']) > 10:
                    split = name.split(' - ')
                    if len(split) > 1:
                        name = rgx_name_feat.sub('', split[1])
                
                    if track.artist != '':
                        search = sp.search(name + ' artist:' + track.artist)
                        if track.album != '' and (len(search['tracks']['items']) == 0 or int(search['tracks']['total']) > 10):
                            search = sp.search(name + ' artist:' + track.artist + ' album:' +  track.album)
                    elif track.album != '':
                        search = sp.search(name + ' album:' +  track.album)
                    elif len(split) > 1:
                        search = sp.search(name)

                    if len(search['tracks']['items']) == 0 and '(' in name:
                        name = rgx_name_parentheses.sub('', name)
                        if track.artist != '':
                            search = sp.search(name + ' artist:' + track.artist)
                            if track.album != '' and (len(search['tracks']['items']) == 0 or int(search['tracks']['total']) > 10):
                                search = sp.search(name + ' artist:' + track.artist + ' album:' +  track.album)
                        elif track.album != '':
                            search = sp.search(name + ' album:' +  track.album)
                        elif len(split) > 1:
                            search = sp.search(name)

                    if track.artist == '' and len(split) > 1:
                        track.artist = rgx_name_parentheses.sub('', split[0].lower())
                elif track.artist != '' or track.album != '':
                    top_item = search['tracks']['items'][0]['id']
                    strict_search = None
                    split = name.split(' - ')
                    if len(split) > 1:
                        name = rgx_name_feat.sub('', split[1])
                    search_str = name
                    new_pick = False
                    if track.artist != '':
                        search_str += ' artist:' + track.artist
                        strict_search = sp.search(search_str)
                        if len(strict_search['tracks']['items']) > 0:
                            search = strict_search
                            if strict_search['tracks']['items'][0]['id'] != top_item:
                                print('(strict search)', end='')
                                new_pick = True
                        else:
                            search_str = name
                    if track.album != '':
                        search_str += ' album:' + track.album
                        strict_search = sp.search(search_str)
                        if len(strict_search['tracks']['items']) > 0:
                            search = strict_search
                            if strict_search['tracks']['items'][0]['id'] != top_item and not new_pick:
                                print('(strict search)', end='')

                strict_matches = [result for result in search['tracks']['items'] if abs(int(result['duration_ms']) - track.length) < 5000 and result['name'].lower().startswith(name)]
                if len(strict_matches) == 1:
                    track.spotify_id = strict_matches[0]['id']
                    buffer.append(track)
                    succeeded.add(track.name + '\r\n')
                    spotify_ids.append(str(track.itunes_id) + ',' + track.spotify_id + '\r\n')
                    to_add += track.spotify_id + ','
                    print('SUCCESS')
                elif len(search['tracks']['items']) == 0 or (track.artist == '' and track.album == '' and int(search['tracks']['total']) > 10):
                    failed.add(track.name + '\r\n')
                    print('FAILED')
                else:
                    matches = [result for result in search['tracks']['items'] if abs(int(result['duration_ms']) - track.length) < 15000]
                    if 'remix' not in name:
                        matches = [match for match in matches if not match['artists'][0]['name'].lower().contains('remix')]

                    if len(matches) > 5 and len(search['tracks']['items']) != len(matches):
                        if len(matches) > 5 and track.artist != '':
                            matches = [match for match in matches if match['artists'][0]['name'].lower() == track.artist.lower()]
                        if len(matches) > 3:
                            split = name.split(' - ')
                            if len(split) > 1:
                                name = split[1]
                            matches = [match for match in matches if match['name'].lower().startswith(name)]

                    if len(matches) == 0:
                        failed.add(track.name + '\r\n')
                        print('FAILED')
                    else:
                        track.spotify_id = matches[0]['id']#sorted(matches, key=lambda item: -int(item['popularity']))[0]['id']
                        buffer.append(track)
                        succeeded.add(track.name + '\r\n')
                        spotify_ids.append(str(track.itunes_id) + ',' + track.spotify_id + '\r\n')
                        to_add += track.spotify_id + ','
                        print('SUCCESS')

print(len(failed), 'failed')
failed_file = open('failed.txt', 'w')
failed_file.writelines(failed)
failed_file.close()

print(len(succeeded), 'succeeded')
succeeded_file = open('succeeded.txt', 'w')
succeeded_file.writelines(succeeded)
succeeded_file.close()

spotify_ids_file = open('spotify_ids.txt', 'w')
spotify_ids_file.writelines(spotify_ids)
spotify_ids_file.close()

to_add_file = open('to_add.txt', 'w')
to_add_file.write(to_add)
to_add_file.close()