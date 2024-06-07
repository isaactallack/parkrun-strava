import strava
import scrape

title, description = scrape.get_title_and_description()
print(title, description)

if title:
    activities = strava.get_activities()

    if len(activities) == 1: # If there is only one matching activity in Strava
        activity_id = activities[0]['id']
        activity_description = strava.get_activity(activity_id)['description']

        if activity_description:
            new_description = f"""{activity_description}

{description}"""
        else:
            new_description = description

        strava.update_activity(activity_id, title, new_description)