import strava
import scrape
import time
import os
import json
from dotenv import load_dotenv

# Define the path to the .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

def load_users(config_file='users.json'):
    with open(os.path.join(os.path.dirname(__file__), config_file), 'r') as file:
        config = json.load(file)
    return config

def save_users(config, config_file='users.json'):
    with open(os.path.join(os.path.dirname(__file__), config_file), 'w') as file:
        json.dump(config, file, indent=4)

def clean_up_old_files(directories, days=7):
    """
    Clean up any html files that are older than 7 days old
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Convert days to seconds
    cutoff_time = time.time() - days * 86400
    
    for directory in directories:
        full_directory_path = os.path.join(current_dir, directory)
        if not os.path.exists(full_directory_path):
            continue
        
        for filename in os.listdir(full_directory_path):
            file_path = os.path.join(full_directory_path, filename)
            if os.path.isfile(file_path) and file_path.endswith('.html'):
                file_created_time = os.path.getctime(file_path)
                if file_created_time < cutoff_time:
                    os.remove(file_path)
                    print(f"Removed old file: {file_path}")

# Clean up old files
directories_to_clean = ['parkruns_files', 'runner_files']
clean_up_old_files(directories_to_clean)

users = load_users()

for account in users['accounts']:
    runner_id = account['RUNNER_ID']
    access_token = account['STRAVA_ACCESS_TOKEN']
    refresh_token = account['STRAVA_REFRESH_TOKEN']
    client_id = account['STRAVA_CLIENT_ID']
    client_secret = account['STRAVA_CLIENT_SECRET']
    expires_at = account['STRAVA_EXPIRES_AT']

    title, description = scrape.get_title_and_description(runner_id)

    if title:
        # Ensure that the token is valid before making API calls
        access_token, refresh_token, expires_at = strava.ensure_valid_token(client_id, client_secret, access_token, refresh_token, expires_at)

        # Update the account with the new tokens
        account['STRAVA_ACCESS_TOKEN'] = access_token
        account['STRAVA_REFRESH_TOKEN'] = refresh_token
        account['STRAVA_EXPIRES_AT'] = expires_at

        activities = strava.get_activities(access_token)

        if len(activities) == 1:
            activity_id = activities[0]['id']
            activity_description = strava.get_activity(access_token, activity_id)['description']

            if activity_description:
                new_description = f"""{activity_description}

{description}"""
            else:
                new_description = description

            strava.update_activity(access_token, activity_id, title, new_description)

# Save updated tokens
save_users(users)