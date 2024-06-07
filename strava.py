import os
import requests
import time
from datetime import datetime, timezone, timedelta
import pytz

def get_current_time():
    spoof_time = os.getenv('SPOOF_TIME')
    if spoof_time == '1':
        spoofed_time_str = os.getenv('SPOOFED_TIME')
        return datetime.strptime(spoofed_time_str, '%Y-%m-%d %H-%M').replace(tzinfo=pytz.timezone('Europe/London'))
    else:
        return datetime.now(pytz.timezone('Europe/London'))

def refresh_access_token(client_id, client_secret, refresh_token):
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

        print('Access token refreshed successfully.')
        return access_token, refresh_token, str(expires_at)
    else:
        print('Failed to refresh access token.')

def ensure_valid_token(client_id, client_secret, access_token, refresh_token, expires_at):
    current_time = int(time.time())
    if not expires_at or current_time >= int(expires_at):
        print('Token expired or not present. Refreshing...')
        access_token, refresh_token, expires_at = refresh_access_token(client_id, client_secret, refresh_token)
    return access_token, refresh_token, expires_at

def get_activities(access_token):
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

def get_activity(access_token, activity_id):
    headers = {'Authorization': f'Bearer {access_token}'}
    
    response = requests.get(f'https://www.strava.com/api/v3/activities/{activity_id}', headers=headers)

    if response.status_code != 200:
        print("Error fetching activities:", response.json())
        return []

    activity = response.json()

    return activity

def update_activity(access_token, activity_id, new_title, new_description):
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
