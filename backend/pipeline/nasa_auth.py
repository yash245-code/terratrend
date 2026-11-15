"""NASA Earthdata authentication helper.

Manages credentials via earthaccess using environment variables, .netrc, or interactive login.
"""
import logging
import os
from typing import Any, Optional
import earthaccess

log = logging.getLogger("teratrend")


def login_earthdata(strategy: str = "environment") -> Any:
    """Authenticate with NASA Earthdata Login.
    
    Tries specified strategy ("environment", "netrc", or "interactive").
    Raises RuntimeError with clear instructions if credentials are not configured.
    """
    try:
        # Check environment variables
        has_env = bool(os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD"))
        chosen_strategy = "environment" if has_env else strategy

        auth = earthaccess.login(strategy=chosen_strategy)
        if auth and auth.authenticated:
            log.info("Successfully authenticated with NASA Earthdata Login.")
            return auth
        else:
            # Fall back to netrc
            log.info("Environment credentials not found or unauthenticated. Trying .netrc...")
            auth_netrc = earthaccess.login(strategy="netrc")
            if auth_netrc and auth_netrc.authenticated:
                log.info("Authenticated via .netrc.")
                return auth_netrc
    except Exception as e:
        log.warning(f"Initial Earthdata login attempt failed: {e}")

    # If still not authenticated
    raise RuntimeError(
        "NASA Earthdata Login authentication failed.\n"
        "Please provide your free NASA Earthdata credentials by:\n"
        "  1) Setting EARTHDATA_USERNAME and EARTHDATA_PASSWORD in your .env file, OR\n"
        "  2) Placing a ~/.netrc file with 'machine urs.earthdata.nasa.gov login <USER> password <PASS>', OR\n"
        "  3) Registering a free account at https://urs.earthdata.nasa.gov/"
    )
