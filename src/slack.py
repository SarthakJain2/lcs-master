import requests
import config
from src import util
from src.schemas import ensure_schema, ensure_logged_in_user
from src.util import add_cors_headers


def create_error_response(err_msg: str):
    return add_cors_headers({"statusCode": 503, "body": err_msg})


def process_slack_error(error_str: str):
    if error_str in ["user_not_found", "user_not_visible", "user_disabled"]:
        return add_cors_headers(
                {"statusCode": 403, "body": f"There was an error with the user id's provided: {error_str}"})
    else:
        return create_error_response(f"Encountered a slack API error: {error_str}")


@ensure_schema({
    "type": "object",
    "properties": {
        "token": {"type": "string"},
        "other_email": {"type": "string", "format": "email"}
    },
    "required": ["token", "other_email"]
})
@ensure_logged_in_user()  # makes sure that the requester is a logged in user
def generate_dm_link(event, context, user=None):
    # attempts to find the other user based on the email provided
    other_user = util.coll("users").find_one({"email": event["other_email"]})
    # ensures that other user exists in LCS
    if other_user is None:
        return add_cors_headers({"statusCode": 403, "body": "Other user not found within LCS"})
    # ensures Slack Token is present in the config
    if "token" not in config.SLACK_KEYS or not config.SLACK_KEYS["token"]:
        return create_error_response("Slack API token not configured")
    # fetches the slack id from their LCS profile
    this_slack_id = user.get("slack_id", None)
    # fetches the other user's slack id from their LCS profile
    other_slack_id = other_user.get("slack_id", None)
    # ensures both id's exist
    if this_slack_id is None or other_slack_id is None:
        return add_cors_headers({"statusCode": 403, "body": "Slack ID not present within LCS for the given user(s)"})
    # creates the link, payload and headers to make the request
    api_link = r"https://slack.com/api/conversations.open"
    slack_api_payload = {"token": config.SLACK_KEYS["token"], "users": f"{this_slack_id},{other_slack_id}"}
    slack_api_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    # calls the API to open a group dm
    response = requests.post(url=api_link, data=slack_api_payload, headers=slack_api_headers)
    # ensures there weren't any errors calling the API
    if response.status_code != 200:
        return create_error_response("Encountered a Slack API error")
    # fetches the json and examines it to determine if it was successful
    response_json = response.json()
    was_successful = response_json["ok"]
    # in case of failure, error message is attached and returned back
    if not was_successful:
        return process_slack_error(response_json["error"])
    # if everything goes well, fetches the necessary id to create the link
    creation_info = response_json["channel"]
    dm_id = creation_info["id"]
    server_id = creation_info["shared_team_ids"][0]
    link_to_dm = f"https://app.slack.com/client/{server_id}/{dm_id}"
    # returns the link and OK status code
    return add_cors_headers({"statusCode": 200, "body": {"slack_dm_link": link_to_dm}})
