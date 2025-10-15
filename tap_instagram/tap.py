"""Instagram tap class."""

from typing import List

import requests
from singer_sdk import Stream, Tap
from singer_sdk import typing as th  # JSON schema typing helpers

from tap_instagram.streams import (
    MediaChildrenStream,
    MediaInsightsStream,
    MediaStream,
    StoriesStream,
    StoryInsightsStream,
    UserInsights28DayStream,
    UserInsightsDailyStream,
    UserInsightsFollowersStream,
    UserInsightsOnlineFollowersStream,
    UserInsightsTotalValueStream,
    UserInsightsWeeklyStream,
    UsersStream,
)

STREAM_TYPES = [
    MediaChildrenStream,
    MediaInsightsStream,
    MediaStream,
    StoriesStream,
    StoryInsightsStream,
    UserInsights28DayStream,
    UserInsightsDailyStream,
    UserInsightsFollowersStream,
    UserInsightsOnlineFollowersStream,
    UserInsightsTotalValueStream,
    UserInsightsWeeklyStream,
    UsersStream,
]

BASE_URL = "https://graph.facebook.com/{ig_user_id}"

session = requests.Session()


class TapInstagram(Tap):
    """Instagram tap class."""

    name = "tap-instagram"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "access_token",
            th.StringType,
            required=True,
            description="A user access token",
        ),
        th.Property(
            "locations",
            th.ArrayType(
                th.ObjectType(
                    th.Property("id", th.StringType, required=True),
                    th.Property("name", th.StringType, required=False),
                )
            ),
            description="List of objects with Instagram user account id (required) and name (optional, for reference only)",
        ),
        th.Property(
            "media_insights_lookback_days",
            th.IntegerType,
            default=60,
            description="The tap fetches media insights for Media objects posted in the last `insights_lookback_days` "
            "days - defaults to 14 days if not provided",
        ),
        th.Property(
            "user_insights_lookback_days",
            th.IntegerType,
            default=90,
            description="The tap fetches user insights for the last `user_insights_lookback_days` days.",
        ),
        th.Property(
            "start_date",
            th.DateTimeType,
            description="The earliest record date to sync",
        ),
        th.Property(
            "metrics_log_level",
            th.StringType,
            description="A user access token",
        ),
    ).to_dict()

    def _get_locations(self) -> List[str]:
        if self.config.get("locations"):
            # Accepts list of objects with "id" and optional "name"
            return [obj["id"] for obj in self.config["locations"] if "id" in obj]
        self.logger.info("`locations` not found in config, fetching from API.")
        url = "https://graph.facebook.com/me/accounts"
        params = {"access_token": self.config["access_token"]}
        response = requests.get(url, params=params)
        response.raise_for_status()
        accounts = response.json()["data"]
        ids = []
        for account in accounts:
            page_id = account["id"]
            page_url = f"https://graph.facebook.com/{page_id}"
            page_params = {
                "fields": "instagram_business_account",
                "access_token": self.config["access_token"],
            }
            page_response = requests.get(page_url, params=page_params)
            page_response.raise_for_status()
            ig_account = page_response.json().get("instagram_business_account")
            if ig_account:
                ids.append(ig_account["id"])
        self.logger.info(f"Found {len(ids)} Instagram accounts.")
        return ids

    @property
    def locations(self) -> List[str]:
        return self._get_locations()

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams."""
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]
