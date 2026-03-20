from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config.settings import settings

logger = logging.getLogger(__name__)

ALL_SCOPES = [
    # Gmail
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    # Drive
    "https://www.googleapis.com/auth/drive",
    # Sheets
    "https://www.googleapis.com/auth/spreadsheets",
    # Docs
    "https://www.googleapis.com/auth/documents",
]


def get_google_credentials() -> Credentials:
    """Load, refresh, or create Google OAuth2 credentials with all required scopes."""
    creds: Credentials | None = None
    token_path: Path = settings.google_token_path
    credentials_path: Path = settings.google_credentials_path

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), ALL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google token")
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Google credentials.json not found at {credentials_path}. "
                    "Download it from Google Cloud Console."
                )
            logger.info("Starting new Google OAuth flow (all scopes)")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), ALL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
        logger.info("Google token saved to %s", token_path)

    return creds
