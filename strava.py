import os
import requests
import time
from dotenv import load_dotenv, set_key
from datetime import datetime, timezone, timedelta
import pytz

def get_current_time():
    spoof_time = os.getenv('SPOOF_TIME')
    if spoof_time == '1':
        spoofed_time_str = os.getenv('SPOOFED_TIME')
        return datetime.strptime(spoofed_time_str, '%Y-%m-%d %H-%M').replace(tzinfo=pytz.timezone('Europe/London'))
    else:
        return datetime.now(pytz.timezone('Europe/London'))

# Define the path to the .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Fetch essential details from environment
client_id = os.getenv('STRAVA_CLIENT_ID')
client_secret = os.getenv('STRAVA_CLIENT_SECRET')
access_token = os.getenv('STRAVA_ACCESS_TOKEN')
refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
expires_at = os.getenv('STRAVA_EXPIRES_AT')

def refresh_access_token():
    global access_token, refresh_token, expires_at

    response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
    )

    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens['refresh_token']
        expires_at = tokens['expires_at']

        # Update .env file
        set_key(dotenv_path, 'STRAVA_ACCESS_TOKEN', access_token)
        set_key(dotenv_path, 'STRAVA_REFRESH_TOKEN', refresh_token)
        set_key(dotenv_path, 'STRAVA_EXPIRES_AT', str(expires_at))

        print('Access token refreshed successfully.')
    else:
        print('Failed to refresh access token.')

def ensure_valid_token():
    global access_token, refresh_token, expires_at

    current_time = int(time.time())
    if not expires_at or current_time >= int(expires_at):
        print('Token expired or not present. Refreshing...')
        refresh_access_token()

# Ensure that the token is valid before making API calls
ensure_valid_token()

def get_activities():
    gmt = pytz.timezone('Europe/London')
    
    start_time_gmt = get_current_time()
    start_time_gmt = start_time_gmt.replace(hour=int(os.getenv('HOUR_LOWER_BOUND')), minute=0, second=0)
    end_time_gmt = start_time_gmt.replace(hour=int(os.getenv('HOUR_UPPER_BOUND')), minute=0, second=0)

    start_time_utc = start_time_gmt.astimezone(pytz.utc)
    end_time_utc = end_time_gmt.astimezone(pytz.utc)

    start_timestamp = int(start_time_utc.timestamp())
    end_timestamp = int(end_time_utc.timestamp())

    headers = {'Authorization': f'Bearer {access_token}'}
    params = {
        'after': start_timestamp,
        'before': end_timestamp,
        'page': 1,
        'per_page': 100
    }
    
    response = requests.get('https://www.strava.com/api/v3/athlete/activities', headers=headers, params=params)

    if response.status_code != 200:
        print("Error fetching activities:", response.json())
        return []

    activities = response.json()

    filtered_activities = [
        activity for activity in activities
        if (start_timestamp <= int(datetime.strptime(activity['start_date'], "%Y-%m-%dT%H:%M:%S%z").timestamp()) <= end_timestamp)
        and (float(os.getenv('LOWER_DISTANCE_LIMIT')) <= activity['distance'] <= float(os.getenv('UPPER_DISTANCE_LIMIT')))
    ]

    return filtered_activities

def get_activity(activity_id):
    headers = {'Authorization': f'Bearer {access_token}'}
    
    response = requests.get(f'https://www.strava.com/api/v3/activities/{activity_id}', headers=headers)

    if response.status_code != 200:
        print("Error fetching activities:", response.json())
        return []

    activity = response.json()

    return activity

def update_activity(activity_id, new_title, new_description):
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {
        "name": new_title,
        "description": new_description
    }

    response = requests.put(url, headers=headers, json=data)

    if response.status_code == 200:
        print("Activity updated successfully.")
        return response.json()
    else:
        print(f"Failed to update the activity: {response.status_code}")
        return response.json()
