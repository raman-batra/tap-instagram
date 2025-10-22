"""REST client handling, including InstagramStream base class."""

import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests
from singer_sdk.exceptions import FatalAPIError, RetriableAPIError
from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.streams import RESTStream

SCHEMAS_DIR = Path(__file__).parent / Path("./schemas")
BASE_URL = "https://graph.facebook.com"


class InstagramStream(RESTStream):
    # TODO: Return the actual error from the Facebook API when fails
    """Instagram stream class."""

    @property
    def url_base(self) -> str:
        """Return the API URL root, configurable via tap settings."""
        return BASE_URL

    records_jsonpath = "$[*]"  # Or override `parse_response`.
    next_page_token_jsonpath = "$.paging.next"  # Or override `get_next_page_token`.

    @property
    def http_headers(self) -> dict:
        """Return the http headers needed."""
        headers = {}
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config.get("user_agent")
        return headers

    def get_next_page_token(
        self, response: requests.Response, previous_token: Optional[Any]
    ) -> Optional[Any]:
        """Return a token for identifying next page or None if no more pages."""
        if self.next_page_token_jsonpath:
            all_matches = extract_jsonpath(
                self.next_page_token_jsonpath, response.json()
            )
            first_match = next(iter(all_matches), None)
            next_page_token = first_match
        else:
            next_page_token = response.headers.get("X-Next-Page", None)

        return next_page_token

    ALLOWED_PARAMS = {
        "access_token",
        "after",
        "before",
        "limit",
        "metric",
        "period",
        "metric_type",
        "fields",
        "since",
        "until",
    }

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        if next_page_token:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(next_page_token).query)
            # Flatten single-item lists and drop unknown params
            cleaned = {}
            for k, v in parsed.items():
                if k in self.ALLOWED_PARAMS:
                    cleaned[k] = v[0] if isinstance(v, list) and len(v) == 1 else v
            return cleaned

        params: dict = {"access_token": self.config["access_token"]}
        if self.replication_key:
            params["sort"] = "asc"
            params["order_by"] = self.replication_key
        return params

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        """Parse the response and return an iterator of result rows."""
        yield from extract_jsonpath(self.records_jsonpath, input=response.json())

    def validate_response(self, response: requests.Response) -> None:
        """
        Custom error handling for Instagram API responses.
        Gracefully handle 400, 502, and 503 by logging and skipping.
        """
        status = response.status_code

        # Handle 400, 502, 503 gracefully: log and skip
        if status in (400, 502, 503):
            try:
                # Try to extract error message if JSON, else fallback to text
                error_message = ""
                try:
                    error_message = response.json().get("error", {}).get("message", "")
                except Exception:
                    error_message = response.text.strip()
                self.logger.warning(
                    f"Skipping record due to {status} error: {error_message} for path: {self.path}"
                )
            except Exception:
                self.logger.warning(
                    f"Skipping record due to {status} error (unable to extract error message) for path: {self.path}"
                )
            return

        # Handle other 4xx as Fatal
        elif 400 < status < 500:
            try:
                error_message = response.json().get("error", {}).get("message", "")
            except Exception:
                error_message = response.text.strip()
            msg = (
                f"{status} Client Error: "
                f"{response.reason} - {error_message}"
                f" for path: {self.path}"
            )
            raise FatalAPIError(msg)

        # Handle other 5xx as Retriable
        elif 500 <= status < 600:
            msg = (
                f"{status} Server Error: "
                f"{response.reason} for path: {self.path}"
            )
            raise RetriableAPIError(msg)

    def get_records(self, context: Optional[dict]) -> Iterable[Dict[str, Any]]:
        """Return a generator of row-type dictionary objects.

        Each row emitted should be a dictionary of property names to their values.

        Args:
            context: Stream partition or context dictionary.

        Yields:
            One item per (possibly processed) record in the API.
        """
        try:
            for record in self.request_records(context):
                transformed_record = self.post_process(record, context)
                if transformed_record is None:
                    # Record filtered out during post_process()
                    continue
                yield transformed_record
        except UnsupportedGetRequestError as e:
            self.logger.warning(e)


class UnsupportedGetRequestError(Exception):
    """
    Error object to facilitate skipping IDs that cause trouble
    with the API but aren't themselves grounds for ending the
    entire ingestion process.
    """
