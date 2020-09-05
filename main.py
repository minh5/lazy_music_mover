import datetime
import logging
import os
import requests

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import more_itertools
import spotipy
import spotipy.util as util


# spotify creds
# TODO: make sure that this can be overridden manually
SPOTIFY_PLAYLISTS = ['Main List', 'Archives']
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_USER_NAME = os.getenv('SPOTIFY_USER_NAME')
SPOTIFY_REDIRECT_URL = os.getenv('SPOTIFY_REDIRECT_URL')

# youtbe creds
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
SCOPE = ["https://www.googleapis.com/auth/youtube"]


def retrieve_playlist_info(headers, playlist_name):
    """Retrieve Spotify playlist information"""
    playlist_url = f'https://api.spotify.com/v1/users/{SPOTIFY_USER_NAME}/playlists'
    res = requests.get(playlist_url, headers=headers)
    res.raise_for_status()
    results = more_itertools.one([
        pl for pl in res.json()['items'] if pl['name'] == playlist_name])
    return results


def get_songs_in_playlist(spotify_api_header, playlist_info):
    """Retrieve the search terms for songs for a single playlist"""
    url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks'
    res = requests.get(url, headers=spotify_api_header)
    res.raise_for_status()
    tracks = res.json()
    search_terms = []

    for track in tracks['items']:
        artists = ' '.join([
            artist['name'] for artist in track['track']['artists']])
        song_name = track['track']['name']
        search_terms.append(f'{song_name} {artists}')

    return search_terms


def retrieve_spotify_info():
    """Authenticate and Retrieve the search terms from the songs by Spotify playlists
    """
    results = {}
    token = util.prompt_for_user_token(
        username=SPOTIFY_USER_NAME,
        scope='playlist-read-private',
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URL)
    spotify_api_header = {'Authorization': f'Bearer {token}'}

    for playlist in SPOTIFY_PLAYLISTS:
        pl_info = retrieve_playlist_info(spotify_api_header, playlist)
        results[playlist] = get_songs_in_playlist(spotify_api_header, pl_info)

    return results


def get_youtube_client():
    """Instaniate and authenticate the Youtube Python Client

    Simply copied from: https://developers.google.com/youtube/v3/docs/playlistItems/list?apix=true
    """
    # Disable OAuthlib's HTTPS verification when running locally.
    # *DO NOT* leave this option enabled in production.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "sync_creds.json"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, SCOPE)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)
    return youtube


def create_playlists(client, playlist_name):
    """Create a Youtube playlist"""
    request = client.playlists().insert(
        part="snippet,status",
        body={
          "snippet": {
            "title": f"{playlist_name}-{datetime.date.today()}",
            "description":
                f"Copy of the {playlist_name} created on {datetime.date.today()}",
            "tags": [
              "API call"
            ],
            "defaultLanguage": "en"
          },
          "status": {
            "privacyStatus": "private"
          }
        }
    )
    response = request.execute()
    return response['id']


def add_song_to_playlist(yt_client, search_terms, playlist_id):
    """Add a song to a given playlist"""
    next_page_token = None
    existing_songs = []

    # retrieve all songs in playlist
    while True:
        request = client.playlistItems().list(
            part='snippet', playlistId=playlist_id, pageToken=next_page_token)
        response = request.execute()
        existing_songs.extend(
            pi['contentDetails']['videoId'] for pi in response['items'])
        next_page_token = response.get('nextPageToken')

        if not next_page_token:
            break


    for term in search_terms:
        logging.info(f'working on {term}')
        request = yt_client.search().list(part='snippet', q=term, type='video')
        response = request.execute()
        video_id = response['items'][0]['id']['videoId']
        request = client.playlistItems().insert(
            part='snippet',
            body={
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        )
        response = request.execute()


def sync_youtube(client, spotify_info):
    """Sync the Youtube playlist given Spotify metadata"""
    for pl in SPOTIFY_PLAYLISTS:
        request = client.playstlis().list(mine=True)
        response = request.execute()
        existing_yt_playlists = [pl['name'] for pl in response['items']]

        if pl in existing_yt_playlists:
            yt_id = more_itertools.one(
                [pl['id'] for pl in response['items'] if pl['name'] == pl])
        else:
            yt_id = create_playlists(client, pl)
        tracks = add_song_to_playlist(client, spotify_info[pl], yt_id)


def main():
    spotify_info = retrieve_spotify_info()
    client = get_youtube_client()
    sync_youtube(client, spotify_info)
