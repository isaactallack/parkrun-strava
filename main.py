import strava
import scrape
import time
import os

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

title, description = scrape.get_title_and_description()
print(title, description)

if title:
    activities = strava.get_activities()

    if len(activities) == 1:
        activity_id = activities[0]['id']
        activity_description = strava.get_activity(activity_id)['description']

        if activity_description:
            new_description = f"""{activity_description}

{description}"""
        else:
            new_description = description

        strava.update_activity(activity_id, title, new_description)