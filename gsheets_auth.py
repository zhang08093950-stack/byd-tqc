#!/usr/bin/env python3
"""Google Sheets authentication — Service Account with Drive warmup for WO spreadsheets."""
import os
import pickle
import socket

# Force IPv4 — Python prefers IPv6 by default, but Google APIs are often
# unreachable over IPv6 from many networks, causing socket.timeout hangs.
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=socket.AF_UNSPEC, *args, **kwargs):
    return _orig_getaddrinfo(host, port, socket.AF_INET, *args, **kwargs)
socket.getaddrinfo = _ipv4_getaddrinfo

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Service Account key (primary) — supports GOOGLE_APPLICATION_CREDENTIALS for Render/cloud
SA_KEY_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.expanduser("~/.claude/credentials/trusty-mantra-494923-u0-5ae64fce221b.json")
)

# OAuth fallback (kept for backward compatibility)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TOKEN_DIR = DATA_DIR
TOKEN_PATH = os.path.join(TOKEN_DIR, "gsheets_token.pickle")
OAUTH_CREDENTIALS_PATH = os.path.join(DATA_DIR, "oauth_client_secret.json")

# Spreadsheets that need Drive warmup before Sheets API access
# Without warmup, these return 404 from Sheets API (Google-side bug)
WARMUP_IDS = {
    "12tRJS2js_Cw4RTZQTGylPjTOemq7lRMsPREzAhuL_Ec",
}


def _warmup_via_drive(creds, spreadsheet_id):
    """Call Drive files().list() to warm up Google's index before Sheets API.

    Some spreadsheets (notably WO&1DC) return 404 from the Sheets API unless
    Drive's search index is queried first. This appears to be a Google-side
    caching/indexing issue where the file's search entry exists but the
    direct API endpoint doesn't resolve without a prior list query.
    """
    if spreadsheet_id not in WARMUP_IDS:
        return
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        drive.files().list(
            q=f"'{spreadsheet_id}' in parents or mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=1,
            fields="files/id",
        ).execute()
    except Exception:
        pass  # warmup is best-effort


def get_service():
    """Authenticate and return a Google Sheets service object.

    Uses Service Account if key file exists, otherwise falls back to OAuth.
    """
    import sys
    print(f"[gsheets] SA_KEY_PATH={SA_KEY_PATH}", file=sys.stderr)
    print(f"[gsheets] exists={os.path.exists(SA_KEY_PATH)}", file=sys.stderr)
    # Prefer Service Account
    if os.path.exists(SA_KEY_PATH):
        creds = service_account.Credentials.from_service_account_file(
            SA_KEY_PATH, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Fallback: OAuth user consent
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise RuntimeError(
            f"Service account key not found at {SA_KEY_PATH}. "
            "Set GOOGLE_APPLICATION_CREDENTIALS or install google-auth-oauthlib."
        )
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_sheet(service, spreadsheet_id, range_name):
    """Read a sheet range. Returns list of rows."""
    _warmup_via_drive(service._http.credentials, spreadsheet_id)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    return result.get("values", [])


def read_sheet_with_formulas(service, spreadsheet_id, range_name):
    """Read a sheet range with formulas instead of computed values."""
    _warmup_via_drive(service._http.credentials, spreadsheet_id)
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueRenderOption="FORMULA",
        )
        .execute()
    )
    return result.get("values", [])
