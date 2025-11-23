import requests
import cloudscraper
from requests_futures.sessions import FuturesSession
from concurrent.futures import as_completed
from fuzzywuzzy import fuzz
import steam.webauth as wa
import time
import pickle
import getpass
import os
import json
import sys
import webbrowser
import logging
import argparse
import configparser
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Generator
from pathlib import Path

# Configure logging
def setup_logging(verbose: bool = False, log_file: str = "humble_redeemer.log") -> logging.Logger:
    """Set up logging with both file and console handlers."""
    logger = logging.getLogger("humble_redeemer")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Clear existing handlers
    logger.handlers = []

    # File handler - always captures DEBUG and above
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # Console handler - respects verbose setting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_format = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    return logger

# Initialize logger (will be reconfigured after args parsing)
logger = setup_logging()

# Configuration management
class Config:
    """Manages application configuration from file and command-line arguments."""
    DEFAULT_CONFIG = {
        'humble': {
            'cookie_file': '.humblecookies',
        },
        'steam': {
            'cookie_file': '.steamcookies',
            'rate_limit_keys_per_hour': '50',
            'rate_limit_failed_per_hour': '10',
        },
        'output': {
            'redeemed_file': 'redeemed.csv',
            'owned_file': 'already_owned.csv',
            'errored_file': 'errored.csv',
            'export_prefix': 'humble_export_',
            'backup_dir': 'backups',
        },
        'settings': {
            'fuzzy_match_threshold': '70',
            'max_concurrent_requests': '30',
            'retry_attempts': '3',
            'retry_delay_seconds': '2',
        }
    }

    def __init__(self, config_file: str = "config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self._load_defaults()
        self._load_from_file()

    def _load_defaults(self):
        """Load default configuration values."""
        for section, options in self.DEFAULT_CONFIG.items():
            self.config[section] = options

    def _load_from_file(self):
        """Load configuration from file if it exists."""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            logger.debug(f"Loaded configuration from {self.config_file}")

    def save(self):
        """Save current configuration to file."""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
        logger.debug(f"Saved configuration to {self.config_file}")

    def get(self, section: str, key: str, fallback: Any = None) -> str:
        """Get a configuration value."""
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        """Get an integer configuration value."""
        return self.config.getint(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        """Get a boolean configuration value."""
        return self.config.getboolean(section, key, fallback=fallback)

# Statistics tracking
class Statistics:
    """Tracks statistics for the current session."""
    def __init__(self):
        self.start_time: datetime = datetime.now()
        self.keys_found: int = 0
        self.keys_redeemed: int = 0
        self.keys_already_owned: int = 0
        self.keys_failed: int = 0
        self.keys_skipped: int = 0
        self.keys_revealed: int = 0
        self.rate_limit_waits: int = 0
        self.errors: List[str] = []

    def add_error(self, error: str):
        """Add an error message to the log."""
        self.errors.append(error)
        logger.error(error)

    def print_summary(self):
        """Print a summary of the session statistics."""
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        print("\n" + "=" * 50)
        print("SESSION SUMMARY")
        print("=" * 50)
        print(f"Duration: {hours}h {minutes}m {seconds}s")
        print(f"Keys found: {self.keys_found}")
        print(f"Keys redeemed: {self.keys_redeemed}")
        print(f"Keys already owned: {self.keys_already_owned}")
        print(f"Keys failed: {self.keys_failed}")
        print(f"Keys skipped: {self.keys_skipped}")
        print(f"Keys revealed: {self.keys_revealed}")
        print(f"Rate limit waits: {self.rate_limit_waits}")
        if self.errors:
            print(f"\nErrors encountered: {len(self.errors)}")
            for error in self.errors[-5:]:  # Show last 5 errors
                print(f"  - {error[:80]}...")
        print("=" * 50)

# Global instances
config = Config()
stats = Statistics()

# Command line argument parsing
def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Humble Bundle Steam Key Redeemer - Automatically extract and redeem Steam keys from Humble Bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Interactive mode
  %(prog)s --mode 1             # Auto-redeem mode
  %(prog)s --mode 2 --export-revealed  # Export revealed keys only
  %(prog)s --dry-run            # Preview without making changes
  %(prog)s --verbose            # Enable debug output
        """
    )

    parser.add_argument('--mode', '-m', type=int, choices=[1, 2, 3],
                        help='Operation mode: 1=Auto-Redeem, 2=Export, 3=Humble Choice')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Preview actions without making changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose/debug output')
    parser.add_argument('--config', '-c', type=str, default='config.ini',
                        help='Path to configuration file')
    parser.add_argument('--reveal-keys', action='store_true',
                        help='Automatically reveal unrevealed keys')
    parser.add_argument('--export-revealed', action='store_true',
                        help='Export only revealed keys')
    parser.add_argument('--export-unrevealed', action='store_true',
                        help='Export only unrevealed keys')
    parser.add_argument('--steam-only', action='store_true',
                        help='Process only Steam keys')
    parser.add_argument('--backup', '-b', action='store_true',
                        help='Create backup before revealing keys')
    parser.add_argument('--resume', '-r', type=str,
                        help='Resume from a previous session file')
    parser.add_argument('--no-steam-check', action='store_true',
                        help='Skip Steam ownership check')

    return parser.parse_args()

# Parse arguments early
args = parse_arguments()

# Reconfigure logging with verbose setting
logger = setup_logging(verbose=args.verbose)

# Reload config if custom path specified
if args.config != 'config.ini':
    config = Config(args.config)


# Retry decorator for network operations
def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0, max_delay: float = 30.0):
    """Decorator for retrying functions with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.RequestException) as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                        raise
                    delay = min(base_delay * (2 ** (retries - 1)), max_delay)
                    logger.warning(f"Retry {retries}/{max_retries} for {func.__name__} after {delay}s: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


def progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> str:
    """Generate a simple text-based progress bar."""
    if total == 0:
        return f"{prefix}[{'=' * width}] 100%"
    percent = current / total
    filled = int(width * percent)
    bar = '=' * filled + '-' * (width - filled)
    return f"{prefix}[{bar}] {percent:.1%} ({current}/{total})"


def create_backup(keys: List[Dict], backup_name: str = None) -> str:
    """Create a backup of keys before processing."""
    backup_dir = config.get('output', 'backup_dir', 'backups')
    Path(backup_dir).mkdir(exist_ok=True)

    if backup_name is None:
        backup_name = f"keys_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    backup_path = os.path.join(backup_dir, backup_name)

    # Create a serializable version of keys
    backup_data = {
        'timestamp': datetime.now().isoformat(),
        'key_count': len(keys),
        'keys': [
            {
                'human_name': k.get('human_name', 'Unknown'),
                'machine_name': k.get('machine_name', ''),
                'steam_app_id': k.get('steam_app_id'),
                'redeemed_key_val': k.get('redeemed_key_val', ''),
                'is_revealed': 'redeemed_key_val' in k,
            }
            for k in keys
        ]
    }

    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2)

    logger.info(f"Backup created: {backup_path}")
    return backup_path


def save_session_state(state: Dict, filename: str = "session_state.json"):
    """Save current session state for resume capability."""
    state['timestamp'] = datetime.now().isoformat()
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    logger.debug(f"Session state saved to {filename}")


def load_session_state(filename: str = "session_state.json") -> Optional[Dict]:
    """Load a previous session state if it exists."""
    if not os.path.exists(filename):
        return None
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            state = json.load(f)
        logger.info(f"Loaded session state from {filename}")
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load session state: {e}")
        return None


# Humble endpoints
HUMBLE_LOGIN_PAGE = "https://www.humblebundle.com/login"
HUMBLE_KEYS_PAGE = "https://www.humblebundle.com/home/library"
HUMBLE_SUB_PAGE = "https://www.humblebundle.com/subscription/"

HUMBLE_LOGIN_API = "https://www.humblebundle.com/processlogin"
HUMBLE_REDEEM_API = "https://www.humblebundle.com/humbler/redeemkey"
HUMBLE_ORDERS_API = "https://www.humblebundle.com/api/v1/user/order"
HUMBLE_ORDER_DETAILS_API = "https://www.humblebundle.com/api/v1/order/"
HUMBLE_SUB_API = "https://www.humblebundle.com/api/v1/subscriptions/humble_monthly/subscription_products_with_gamekeys/"

HUMBLE_PAY_EARLY = "https://www.humblebundle.com/subscription/payearly"
HUMBLE_CHOOSE_CONTENT = "https://www.humblebundle.com/humbler/choosecontent"

# Steam endpoints
STEAM_KEYS_PAGE = "https://store.steampowered.com/account/registerkey"
STEAM_USERDATA_API = "https://store.steampowered.com/dynamicstore/userdata/"
STEAM_REDEEM_API = "https://store.steampowered.com/account/ajaxregisterkey/"
STEAM_APP_LIST_API = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"

# May actually be able to do without these, but for now they're in.
headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def find_dict_keys(node, kv, parent=False):
    if isinstance(node, list):
        for i in node:
            for x in find_dict_keys(i, kv, parent):
               yield x
    elif isinstance(node, dict):
        if kv in node:
            if parent:
                yield node
            else:
                yield node[kv]
        for j in node.values():
            for x in find_dict_keys(j, kv, parent):
                yield x


MODE_PROMPT = """Welcome to the Humble Exporter!
Which key export mode would you like to use?

[1] Auto-Redeem
[2] Export keys
[3] Humble Choice chooser
"""
def prompt_mode(order_details,humble_session):
    mode = None
    while mode not in ["1","2","3"]:
        print(MODE_PROMPT)
        mode = input("Choose 1, 2, or 3: ").strip()
        if mode in ["1","2","3"]:
            return mode
        else:
            print("Invalid mode")
    return mode


def valid_steam_key(key: Any) -> bool:
    """Validate that a string is a valid Steam key format (XXXXX-XXXXX-XXXXX)."""
    if not isinstance(key, str):
        return False
    key_parts = key.split("-")
    return (
        len(key) == 17
        and len(key_parts) == 3
        and all([len(part) == 5 for part in key_parts])
    )


def try_recover_cookies(cookie_file: str, session: requests.Session) -> bool:
    """Attempt to recover session cookies from a pickle file."""
    try:
        with open(cookie_file, "rb") as file:
            session.cookies.update(pickle.load(file))
        logger.debug(f"Recovered cookies from {cookie_file}")
        return True
    except FileNotFoundError:
        logger.debug(f"Cookie file {cookie_file} not found")
        return False
    except (pickle.UnpicklingError, EOFError) as e:
        logger.warning(f"Corrupted cookie file {cookie_file}: {e}")
        return False
    except PermissionError as e:
        logger.error(f"Permission denied reading {cookie_file}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error loading cookies from {cookie_file}: {e}")
        return False


def export_cookies(cookie_file: str, session: requests.Session) -> bool:
    """Export session cookies to a pickle file."""
    try:
        with open(cookie_file, "wb") as file:
            pickle.dump(session.cookies, file)
        logger.debug(f"Exported cookies to {cookie_file}")
        return True
    except PermissionError as e:
        logger.error(f"Permission denied writing to {cookie_file}: {e}")
        return False
    except IOError as e:
        logger.error(f"IO error writing cookies to {cookie_file}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error saving cookies to {cookie_file}: {e}")
        return False


def verify_logins_session(session: requests.Session) -> Tuple[bool, bool]:
    """Verify if sessions are still valid for Humble and Steam.

    Returns: Tuple of (humble_logged_in, steam_logged_in)
    """
    loggedin = []
    for url in [HUMBLE_KEYS_PAGE, STEAM_KEYS_PAGE]:
        try:
            r = session.get(url, allow_redirects=False, timeout=30)
            loggedin.append(r.status_code != 301 and r.status_code != 302)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error verifying session for {url}: {e}")
            loggedin.append(False)
    return tuple(loggedin)


def humble_login(session: cloudscraper.CloudScraper) -> bool:
    """Authenticate with Humble Bundle.

    Args:
        session: CloudScraper session to use for authentication

    Returns:
        True if authentication was successful
    """
    cls()
    cookie_file = config.get('humble', 'cookie_file', '.humblecookies')

    # Attempt to use saved session
    if try_recover_cookies(cookie_file, session) and verify_logins_session(session)[0]:
        headers["CSRF-Prevention-Token"] = session.cookies["csrf_cookie"]
        logger.info("Recovered existing Humble Bundle session")
        return True
    else:
        session.cookies.clear()

    # Saved session didn't work
    logger.info("Please log in to Humble Bundle")
    authorized = False
    auth = None

    while not authorized:
        username = input("Humble Email: ")
        password = getpass.getpass("Password: ")

        try:
            csrf_req = session.get(HUMBLE_LOGIN_PAGE, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Humble Bundle: {e}")
            continue

        payload = {
            "access_token": "",
            "access_token_provider_id": "",
            "goto": "/",
            "qs": "",
            "username": username,
            "password": password,
        }
        headers["CSRF-Prevention-Token"] = session.cookies["csrf_cookie"]

        try:
            r = session.post(HUMBLE_LOGIN_API, data=payload, headers=headers, timeout=30)
            login_json = r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Login request failed: {e}")
            continue
        except json.JSONDecodeError as e:
            logger.error(f"Invalid response from Humble Bundle: {e}")
            continue

        if "errors" in login_json and "username" in login_json["errors"]:
            # Unknown email OR mismatched password
            logger.warning(login_json["errors"]["username"][0])
            continue

        while "humble_guard_required" in login_json or "two_factor_required" in login_json:
            # There may be differences for Humble's SMS 2FA, haven't tested.
            if "humble_guard_required" in login_json:
                humble_guard_code = input("Please enter the Humble security code: ")
                payload["guard"] = humble_guard_code.upper()
                # Humble security codes are case-sensitive via API, but luckily it's all uppercase!
                try:
                    auth = session.post(HUMBLE_LOGIN_API, data=payload, headers=headers, timeout=30)
                    login_json = auth.json()
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    logger.error(f"2FA request failed: {e}")
                    break

                if (
                    "user_terms_opt_in_data" in login_json
                    and login_json["user_terms_opt_in_data"]["needs_to_opt_in"]
                ):
                    logger.error("There's been an update to the TOS, please sign in to Humble on your browser.")
                    sys.exit(1)
            elif (
                "two_factor_required" in login_json and
                "errors" in login_json
                and "authy-input" in login_json["errors"]
            ):
                code = input("Please enter 2FA code: ")
                payload["code"] = code
                try:
                    auth = session.post(HUMBLE_LOGIN_API, data=payload, headers=headers, timeout=30)
                    login_json = auth.json()
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    logger.error(f"2FA request failed: {e}")
                    break
            elif "errors" in login_json:
                logger.error(f"Unexpected login error: {login_json['errors']}")
                sys.exit(1)

            if auth is not None and auth.status_code == 200:
                break

        export_cookies(cookie_file, session)
        logger.info("Successfully authenticated with Humble Bundle")
        return True


def steam_login() -> requests.Session:
    """Sign into Steam web.

    Returns:
        Authenticated requests Session
    """
    cookie_file = config.get('steam', 'cookie_file', '.steamcookies')

    # Attempt to use saved session
    r = requests.Session()
    if try_recover_cookies(cookie_file, r) and verify_logins_session(r)[1]:
        logger.info("Recovered existing Steam session")
        return r

    # Saved state doesn't work, prompt user to sign in.
    logger.info("Please log in to Steam")
    s_username = input("Steam Username: ")

    try:
        user = wa.WebAuth(s_username)
        session = user.cli_login()
        export_cookies(cookie_file, session)
        logger.info("Successfully authenticated with Steam")
        return session
    except Exception as e:
        logger.error(f"Steam authentication failed: {e}")
        raise


def redeem_humble_key(sess: cloudscraper.CloudScraper, tpk: Dict[str, Any], dry_run: bool = False) -> str:
    """Redeem a key on Humble Bundle to get the Steam key.

    Keys need to be 'redeemed' on Humble first before the Humble API gives the user a Steam key.
    This triggers that for a given Humble key entry.

    Args:
        sess: Authenticated CloudScraper session
        tpk: The key data from Humble Bundle
        dry_run: If True, don't actually redeem the key

    Returns:
        The Steam key string, or empty string on failure
    """
    game_name = tpk.get("human_name", "Unknown")

    if dry_run:
        logger.info(f"[DRY RUN] Would reveal key for: {game_name}")
        return ""

    payload = {"keytype": tpk["machine_name"], "key": tpk["gamekey"], "keyindex": tpk["keyindex"]}

    try:
        resp = sess.post(HUMBLE_REDEEM_API, data=payload, headers=headers, timeout=30)
        logger.debug(f"Humble redeem response: {resp.text[:200]}...")

        respjson = resp.json()

        if resp.status_code != 200 or "error_msg" in respjson or not respjson.get("success", False):
            error_msg = respjson.get("error_msg", "Unknown error")
            logger.error(f"Error redeeming key on Humble for {game_name}: {error_msg}")
            stats.add_error(f"Humble redeem failed for {game_name}: {error_msg}")
            return ""

        stats.keys_revealed += 1
        return respjson.get("key", "")

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error redeeming {game_name} on Humble: {e}")
        stats.add_error(f"Network error for {game_name}: {e}")
        return ""
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response for {game_name}: {e}")
        stats.add_error(f"Invalid response for {game_name}")
        return ""
    except KeyError as e:
        logger.error(f"Missing expected key in response for {game_name}: {e}")
        return ""


def get_month_data(humble_session,month):
    # No real API for this, seems to just be served on the webpage.
    r = humble_session.get(HUMBLE_SUB_PAGE + month["product"]["choice_url"])

    data_indicator = f'<script id="webpack-monthly-product-data" type="application/json">'
    jsondata = r.text.split(data_indicator)[1].split("</script>")[0].strip()
    jsondata = json.loads(jsondata)
    return jsondata["contentChoiceOptions"]


def get_choices(humble_session,order_details):
    months = [
        month for month in order_details 
        if "is_humble_choice" in month["product"] and 
        month["product"]["is_humble_choice"]
    ]

    # Oldest to Newest order
    months = sorted(months,key=lambda m: m["created"])

    choices = []
    for month in months:
        if month["choices_remaining"] > 0:
            chosen_games = set(find_dict_keys(month["tpkd_dict"],"machine_name"))

            month["choice_data"] = get_month_data(humble_session,month)
            
            # Needed for choosing
            identifier = "initial" if "initial" in month["choice_data"]["contentChoiceData"] else "initial-classic"
            
            if identifier not in month["choice_data"]["contentChoiceData"]:
                for key in month["choice_data"]["contentChoiceData"].keys():
                    if "content_choices" in month["choice_data"]["contentChoiceData"][key]:
                        identifier = key
            choice_options = month["choice_data"]["contentChoiceData"][identifier]["content_choices"]

            # Exclude games that have already been chosen:
            month["available_choices"] = [
                    game[1]
                    for game in choice_options.items()
                    if set(find_dict_keys(game[1],"machine_name")).isdisjoint(chosen_games)
            ]
            
            month["parent_identifier"] = identifier
            yield month


# Steam error code messages
STEAM_ERROR_MESSAGES: Dict[int, str] = {
    14: "The product code you've entered is not valid. Please double check to see if you've "
        "mistyped your key. I, L, and 1 can look alike, as can V and Y, and 0 and O.",
    15: "The product code you've entered has already been activated by a different Steam account. "
        "This code cannot be used again. Please contact the retailer or online seller where the "
        "code was purchased for assistance.",
    53: "There have been too many recent activation attempts from this account or Internet "
        "address. Please wait and try your product code again later.",
    13: "Sorry, but this product is not available for purchase in this country. Your product key "
        "has not been redeemed.",
    9: "This Steam account already owns the product(s) contained in this offer. To access them, "
       "visit your library in the Steam client.",
    24: "The product code you've entered requires ownership of another product before "
        "activation. If you are trying to activate an expansion pack or downloadable content, "
        "please first activate the original game, then activate this additional content.",
    36: "The product code you have entered requires that you first play this game on the "
        "PlayStation 3 system before it can be registered.",
    50: "The code you have entered is from a Steam Gift Card or Steam Wallet Code. Browse here: "
        "https://store.steampowered.com/account/redeemwalletcode to redeem it.",
}

STEAM_ERROR_DEFAULT = (
    "An unexpected error has occurred. Your product code has not been redeemed. Please wait "
    "30 minutes and try redeeming the code again. If the problem persists, please contact "
    "Steam Support for further assistance."
)


def _redeem_steam(session: requests.Session, key: str, quiet: bool = False, dry_run: bool = False) -> int:
    """Redeem a product key on Steam.

    Based on https://gist.github.com/snipplets/2156576c2754f8a4c9b43ccb674d5a5d

    Args:
        session: Authenticated Steam session
        key: The Steam product key to redeem
        quiet: If True, suppress rate limit messages
        dry_run: If True, don't actually redeem the key

    Returns:
        Error code (0 = success)
    """
    if key == "":
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would redeem Steam key: {key[:5]}*****")
        return 0

    try:
        session_id = session.cookies.get_dict()["sessionid"]
        r = session.post(STEAM_REDEEM_API, data={"product_key": key, "sessionid": session_id}, timeout=30)
        blob = r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error redeeming Steam key: {e}")
        return 53  # Treat as rate limit to trigger retry
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Invalid response from Steam: {e}")
        return -1

    if blob.get("success") == 1:
        for item in blob.get("purchase_receipt_info", {}).get("line_items", []):
            logger.info(f"Redeemed: {item.get('line_item_description', 'Unknown')}")
            stats.keys_redeemed += 1
        return 0
    else:
        error_code = blob.get("purchase_result_details")
        if error_code is None:
            # Sometimes purchase_result_details isn't there for some reason, try alt method
            purchase_info = blob.get("purchase_receipt_info")
            if purchase_info is not None:
                error_code = purchase_info.get("result_detail")
        error_code = error_code or 53

        error_message = STEAM_ERROR_MESSAGES.get(error_code, STEAM_ERROR_DEFAULT)

        if error_code != 53 or not quiet:
            logger.warning(f"Steam error {error_code}: {error_message}")

        # Track statistics
        if error_code == 9 or error_code == 15:
            stats.keys_already_owned += 1
        elif error_code == 53:
            stats.rate_limit_waits += 1
        else:
            stats.keys_failed += 1

        return error_code


files: Dict[str, Any] = {}


def write_key(code: int, key: Dict[str, Any], dry_run: bool = False) -> None:
    """Write a key to the appropriate CSV file based on its redemption status.

    Args:
        code: Steam error code (0 = success)
        key: Key data dictionary
        dry_run: If True, don't actually write to file
    """
    global files

    if dry_run:
        logger.debug(f"[DRY RUN] Would write key {key.get('human_name')} with code {code}")
        return

    filename = config.get('output', 'redeemed_file', 'redeemed.csv')
    if code == 15 or code == 9:
        filename = config.get('output', 'owned_file', 'already_owned.csv')
    elif code != 0:
        filename = config.get('output', 'errored_file', 'errored.csv')

    if filename not in files:
        try:
            files[filename] = open(filename, "a", encoding="utf-8-sig")
        except IOError as e:
            logger.error(f"Failed to open {filename} for writing: {e}")
            return

    # Sanitize the human name (replace commas for CSV compatibility)
    human_name = key.get("human_name", "Unknown").replace(",", ".")
    gamekey = key.get('gamekey', '')
    redeemed_key_val = key.get("redeemed_key_val", '')

    output = f"{gamekey},{human_name},{redeemed_key_val}\n"

    try:
        files[filename].write(output)
        files[filename].flush()
        logger.debug(f"Wrote key for {human_name} to {filename}")
    except IOError as e:
        logger.error(f"Failed to write to {filename}: {e}")


def prompt_skipped(skipped_games: Dict[str, Dict]) -> List[Dict]:
    """Prompt user to review potentially owned games.

    Creates a file with skipped games that user can edit to include games
    they want to try redeeming anyway.

    Args:
        skipped_games: Dictionary of game names to game data

    Returns:
        List of games the user wants to try redeeming
    """
    user_filtered = []

    try:
        with open("skipped.txt", "w", encoding="utf-8-sig") as file:
            for skipped_game in skipped_games.keys():
                file.write(skipped_game + "\n")
    except IOError as e:
        logger.error(f"Failed to create skipped.txt: {e}")
        return []

    logger.info(
        f"Inside skipped.txt is a list of {len(skipped_games)} games that we think you already own, "
        f"but aren't completely sure."
    )

    try:
        input(
            "Feel free to REMOVE from that list any games that you would like to try anyways, "
            "and when done press Enter to confirm. "
        )
    except (KeyboardInterrupt, EOFError):
        logger.info("User cancelled skipped games review")
        pass

    if os.path.exists("skipped.txt"):
        try:
            with open("skipped.txt", "r", encoding="utf-8-sig") as file:
                user_filtered = [line.strip() for line in file]
            os.remove("skipped.txt")
        except IOError as e:
            logger.error(f"Failed to read skipped.txt: {e}")

    # Choose only the games that appear to be missing from user's skipped.txt file
    user_requested = [
        skip_game
        for skip_name, skip_game in skipped_games.items()
        if skip_name not in user_filtered
    ]

    logger.info(f"User requested {len(user_requested)} additional games from skipped list")
    return user_requested


def prompt_yes_no(question):
    ans = None
    answers = ["y","n"]
    while ans not in answers:
        prompt = f"{question} [{'/'.join(answers)}] "

        ans = input(prompt).strip().lower()
        if ans not in answers:
            print(f"{ans} is not a valid answer")
            continue
        else:
            return True if ans == "y" else False

def get_owned_apps(steam_session: requests.Session) -> Dict[int, str]:
    """Get all owned apps from Steam.

    Args:
        steam_session: Authenticated Steam session

    Returns:
        Dictionary mapping app IDs to app names
    """
    try:
        owned_content = steam_session.get(STEAM_USERDATA_API, timeout=30).json()
        owned_app_ids = owned_content.get("rgOwnedPackages", []) + owned_content.get("rgOwnedApps", [])

        app_list_response = steam_session.get(STEAM_APP_LIST_API, timeout=60).json()
        owned_app_details = {
            app["appid"]: app["name"]
            for app in app_list_response.get("applist", {}).get("apps", [])
            if app["appid"] in owned_app_ids
        }
        logger.debug(f"Found {len(owned_app_details)} owned apps on Steam")
        return owned_app_details
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch owned apps from Steam: {e}")
        return {}
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Invalid response from Steam: {e}")
        return {}


def match_ownership(owned_app_details: Dict[int, str], game: Dict[str, Any]) -> Tuple[int, Optional[int]]:
    """Match a game name against owned apps using fuzzy matching.

    Args:
        owned_app_details: Dictionary of owned app IDs to names
        game: Game data with human_name field

    Returns:
        Tuple of (match_score, app_id) or (0, None) if no match
    """
    threshold = config.getint('settings', 'fuzzy_match_threshold', 70)
    best_match = (0, None)

    # Do a string search based on product names.
    matches = [
        (fuzz.token_set_ratio(appname, game["human_name"]), appid)
        for appid, appname in owned_app_details.items()
    ]
    refined_matches = [
        (fuzz.token_sort_ratio(owned_app_details[appid], game["human_name"]), appid)
        for score, appid in matches
        if score > threshold
    ]

    if len(refined_matches) > 0:
        best_match = max(refined_matches, key=lambda item: item[0])
    elif len(refined_matches) == 1:
        best_match = refined_matches[0]

    if best_match[0] < 35:
        best_match = (0, None)

    return best_match


def redeem_steam_keys(humble_session: cloudscraper.CloudScraper, humble_keys: List[Dict],
                      dry_run: bool = False, skip_steam_check: bool = False) -> None:
    """Redeem Steam keys from Humble Bundle.

    Args:
        humble_session: Authenticated Humble Bundle session
        humble_keys: List of keys to redeem
        dry_run: If True, don't actually redeem keys
        skip_steam_check: If True, skip Steam ownership check
    """
    stats.keys_found = len(humble_keys)

    if dry_run:
        logger.info("[DRY RUN] Would log into Steam")
        session = None
        owned_app_details = {}
    else:
        session = steam_login()
        logger.info("Successfully signed in on Steam.")

        if skip_steam_check:
            logger.info("Skipping Steam ownership check as requested")
            owned_app_details = {}
        else:
            logger.info("Getting your owned content to avoid attempting to register keys already owned...")
            owned_app_details = get_owned_apps(session)

    noted_keys = [key for key in humble_keys if key.get("steam_app_id") not in owned_app_details.keys()]
    skipped_games = {}
    unownedgames = []

    # Some Steam keys come back with no Steam AppID from Humble
    # So we do our best to look up from AppIDs (no packages, because can't find an API for it)
    logger.info("Checking ownership via fuzzy matching...")
    for i, game in enumerate(noted_keys):
        if i % 50 == 0:
            print(f"\r{progress_bar(i, len(noted_keys), prefix='Checking ownership: ')}", end="")
        best_match = match_ownership(owned_app_details, game)
        if best_match[1] is not None and best_match[1] in owned_app_details.keys():
            skipped_games[game["human_name"].strip()] = game
        else:
            unownedgames.append(game)
    print()  # Clear progress line

    logger.info(f"Filtered out game keys that you already own on Steam; {len(unownedgames)} keys unowned.")

    if len(skipped_games) and not dry_run:
        # Skipped games uncertain to be owned by user. Let user choose
        unownedgames = unownedgames + prompt_skipped(skipped_games)
        logger.info(f"{len(unownedgames)} keys will be attempted.")
        # Preserve original order
        unownedgames = sorted(unownedgames, key=lambda g: humble_keys.index(g))

    redeemed = []
    total_keys = len(unownedgames)

    for idx, key in enumerate(unownedgames):
        game_name = key.get("human_name", "Unknown")
        print(f"\r{progress_bar(idx + 1, total_keys, prefix='Redeeming: ')} - {game_name[:30]}", end="")
        logger.debug(f"Processing: {game_name}")

        if game_name in redeemed or (key.get("steam_app_id") is not None and key["steam_app_id"] in redeemed):
            # We've bumped into a repeat of the same game!
            write_key(9, key, dry_run=dry_run)
            stats.keys_skipped += 1
            continue
        else:
            if key.get("steam_app_id") is not None:
                redeemed.append(key["steam_app_id"])
            redeemed.append(game_name)

        if "redeemed_key_val" not in key:
            # This key is unredeemed via Humble, trigger redemption process.
            redeemed_key = redeem_humble_key(humble_session, key, dry_run=dry_run)
            key["redeemed_key_val"] = redeemed_key
            # Worth noting this will only persist for this loop -- does not get saved to unownedgames' obj

        if not valid_steam_key(key.get("redeemed_key_val", "")):
            # Most likely humble gift link
            write_key(1, key, dry_run=dry_run)
            stats.keys_skipped += 1
            continue

        if dry_run:
            logger.info(f"[DRY RUN] Would redeem: {game_name}")
            continue

        code = _redeem_steam(session, key["redeemed_key_val"], dry_run=dry_run)
        animation = "|/-\\"
        seconds = 0

        while code == 53:
            # Steam rate limit (50 keys/hr or 10 failed keys/hr)
            current_animation = animation[seconds % len(animation)]
            elapsed_mins = seconds // 60
            print(
                f"\rRate limited - waiting... [{elapsed_mins}m elapsed] {current_animation}   ",
                end="",
            )
            time.sleep(1)
            seconds += 1
            if seconds % 60 == 0:
                # Try again every 60 seconds
                code = _redeem_steam(session, key["redeemed_key_val"], quiet=True, dry_run=dry_run)

        write_key(code, key, dry_run=dry_run)

        # Save session state periodically for resume capability
        if idx % 10 == 0:
            save_session_state({
                'last_processed_index': idx,
                'total_keys': total_keys,
                'redeemed': redeemed,
            })

    print()  # Clear progress line
    logger.info("Key redemption complete!")


def export_mode(humble_session,order_details):
    cls()

    export_key_headers = ['human_name','redeemed_key_val','is_gift','key_type_human_name','is_expired','steam_ownership']

    steam_session = None
    reveal_unrevealed = False
    confirm_reveal = False

    owned_app_details = None

    keys = []
    
    print("Please configure your export:")
    export_steam_only = prompt_yes_no("Export only Steam keys?")
    export_revealed = prompt_yes_no("Export revealed keys?")
    export_unrevealed = prompt_yes_no("Export unrevealed keys?")
    if(not export_revealed and not export_unrevealed):
        print("That leaves 0 keys...")
        sys.exit()
    if(export_unrevealed):
        reveal_unrevealed = prompt_yes_no("Reveal all unrevealed keys? (This will remove your ability to claim gift links on these)")
        if(reveal_unrevealed):
            extra = "Steam " if export_steam_only else ""
            confirm_reveal = prompt_yes_no(f"Please CONFIRM that you would like ALL {extra}keys on Humble to be revealed, this can't be undone.")
    steam_config = prompt_yes_no("Would you like to sign into Steam to detect ownership on the export data?")
    
    if(steam_config):
        steam_session = steam_login()
        if(verify_logins_session(steam_session)[1]):
            owned_app_details = get_owned_apps(steam_session)
    
    desired_keys = "steam_app_id" if export_steam_only else "key_type_human_name"
    keylist = list(find_dict_keys(order_details,desired_keys,True))

    for idx,tpk in enumerate(keylist):
        revealed = "redeemed_key_val" in tpk
        export = (export_revealed and revealed) or (export_unrevealed and not revealed)

        if(export):
            if(export_unrevealed and confirm_reveal):
                # Redeem key if user requests all keys to be revealed
                tpk["redeemed_key_val"] = redeem_humble_key(humble_session,tpk)
            
            if(owned_app_details != None and "steam_app_id" in tpk):
                # User requested Steam Ownership info
                owned = tpk["steam_app_id"] in owned_app_details.keys()
                if(not owned):
                    # Do a search to see if user owns it
                    best_match = match_ownership(owned_app_details,tpk)
                    owned = best_match[1] is not None and best_match[1] in owned_app_details.keys()
                tpk["steam_ownership"] = owned
            
            keys.append(tpk)
    
    ts = time.strftime("%Y%m%d-%H%M%S")
    filename = f"humble_export_{ts}.csv"
    with open(filename, 'w', encoding="utf-8-sig") as f:
        f.write(','.join(export_key_headers)+"\n")
        for key in keys:
            row = []
            for col in export_key_headers:
                if col in key:
                    row.append("\"" + str(key[col]) + "\"")
                else:
                    row.append("")
            f.write(','.join(row)+"\n")
    
    print(f"Exported to {filename}")


def choose_games(humble_session,choice_month_name,identifier,chosen):
    for choice in chosen:
        display_name = choice["display_item_machine_name"]
        if "tpkds" not in choice:
            webbrowser.open(f"{HUMBLE_SUB_PAGE}{choice_month_name}/{display_name}")
        else:
            payload = {
                "gamekey":choice["tpkds"][0]["gamekey"],
                "parent_identifier":identifier,
                "chosen_identifiers[]":display_name,
                "is_multikey_and_from_choice_modal":"false"
            }
            res = humble_session.post(HUMBLE_CHOOSE_CONTENT,data=payload,headers=headers).json()
            if not ("success" in res or not res["success"]):
                print("Error choosing " + choice["title"])
                print(res)
            else:
                print("Chose game " + choice["title"])


def humble_chooser_mode(humble_session,order_details):
    try_redeem_keys = []
    months = get_choices(humble_session,order_details)
    count = 0
    first = True
    for month in months:
        redeem_all = None
        if(first):
            redeem_keys = prompt_yes_no("Would you like to auto-redeem these keys after? (Will require Steam login)")
            first = False
        
        ready = False
        while not ready:
            cls()
            remaining = month["choices_remaining"]
            print()
            print(month["product"]["human_name"])
            print(f"Choices remaining: {remaining}")
            print("Available Games:\n")
            choices = month["available_choices"]
            for idx,choice in enumerate(choices):
                title = choice["title"]
                rating_text = ""
                if("review_text" in choice["user_rating"] and "steam_percent|decimal" in choice["user_rating"]):
                    rating = choice["user_rating"]["review_text"].replace('_',' ')
                    percentage = str(int(choice["user_rating"]["steam_percent|decimal"]*100)) + "%"
                    rating_text = f" - {rating}({percentage})"
                exception = ""
                if "tpkds" not in choice:
                    # These are weird cases that should be handled by Humble.
                    exception = " (Must be redeemed through Humble directly)"
                print(f"{idx+1}. {title}{rating_text}{exception}")
            if(redeem_all == None and remaining == len(choices)):
                redeem_all = prompt_yes_no("Would you like to redeem all?")
            else:
                redeem_all = False
            
            if(redeem_all):
                user_input = [str(i+1) for i in range(0,len(choices))]
            else:
                if(redeem_keys):
                    auto_redeem_note = "(We'll auto-redeem any keys activated via the webpage if you continue after!)"
                else:
                    auto_redeem_note = ""
                print("\nOPTIONS:")
                print("To choose games, list the indexes separated by commas (e.g. '1' or '1,2,3')")
                print(f"Or type just 'link' to go to the webpage for this month {auto_redeem_note}")
                print("Or just press Enter to move on.")

                user_input = [uinput.strip() for uinput in input().split(',') if uinput.strip() != ""]

            if(len(user_input) == 0):
                ready = True
            elif(user_input[0].lower() == 'link'):
                webbrowser.open(HUMBLE_SUB_PAGE + month["product"]["choice_url"])
                if redeem_keys:
                    # May have redeemed keys on the webpage.
                    try_redeem_keys.append(month["gamekey"])
            else:
                invalid_option = lambda option: (
                    not option.isnumeric()
                    or option == "0" 
                    or int(option) > len(choices)
                )
                invalid = [option for option in user_input if invalid_option(option)]

                if(len(invalid) > 0):
                    print("Error interpreting options: " + ','.join(invalid))
                    time.sleep(2)
                else:
                    user_input = set(int(opt) for opt in user_input) # Uniques
                    chosen = [choice for idx,choice in enumerate(choices) if idx+1 in user_input]
                    # This weird enumeration is to keep it in original display order

                    if len(chosen) > remaining:
                        print(f"Too many games chosen, you have only {remaining} choices left")
                        time.sleep(2)
                    else:
                        print("\nGames selected:")
                        for choice in chosen:
                            print(choice["title"])
                        confirmed = prompt_yes_no("Please type 'y' to confirm your selection")
                        if confirmed:
                            choice_month_name = month["product"]["choice_url"]
                            identifier = month["parent_identifier"]
                            choose_games(humble_session,choice_month_name,identifier,chosen)
                            if redeem_keys:
                                try_redeem_keys.append(month["gamekey"])
                            ready = True
    if(first):
        print("No Humble Choices need choosing! Look at you all up-to-date!")
    else:
        print("No more unchosen Humble Choices")
        if(redeem_keys and len(try_redeem_keys) > 0):
            print("Redeeming keys now!")
            updated_monthlies = [
                humble_session.get(f"{HUMBLE_ORDER_DETAILS_API}{order}?all_tpkds=true").json()
                for order in try_redeem_keys
            ]
            chosen_keys = list(find_dict_keys(updated_monthlies,"steam_app_id",True))
            redeem_steam_keys(humble_session,chosen_keys)

def cls():
    """Clear the terminal screen and print the header."""
    os.system('cls' if os.name=='nt' else 'clear')
    print_main_header()


def print_main_header():
    """Print the application header."""
    print("-=FailSpy's Humble Bundle Helper!=-")
    print("--------------------------------------")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]")
        print("--------------------------------------")


def filter_previous_keys(steam_keys: List[Dict]) -> List[Dict]:
    """Filter out keys that were processed in previous runs.

    Args:
        steam_keys: List of Steam keys to filter

    Returns:
        Filtered list of keys
    """
    filters = [
        config.get('output', 'errored_file', 'errored.csv'),
        config.get('output', 'owned_file', 'already_owned.csv'),
        config.get('output', 'redeemed_file', 'redeemed.csv'),
    ]
    original_length = len(steam_keys)

    for filter_file in filters:
        try:
            with open(filter_file, "r", encoding="utf-8-sig") as f:
                keycols = f.read()
            filtered_keys = [keycol.strip() for keycol in keycols.replace("\n", ",").split(",") if keycol.strip()]
            steam_keys = [key for key in steam_keys if key.get("gamekey") not in filtered_keys]
        except FileNotFoundError:
            logger.debug(f"Filter file {filter_file} not found (this is normal for first run)")
        except IOError as e:
            logger.warning(f"Could not read filter file {filter_file}: {e}")

    if len(steam_keys) != original_length:
        logger.info(f"Filtered {original_length - len(steam_keys)} keys from previous runs")

    return steam_keys


def fetch_order_details(humble_session: cloudscraper.CloudScraper, orders: List[Dict]) -> List[Dict]:
    """Fetch detailed order information with progress tracking.

    Args:
        humble_session: Authenticated Humble Bundle session
        orders: List of order summaries

    Returns:
        List of detailed order information
    """
    max_workers = config.getint('settings', 'max_concurrent_requests', 30)
    order_details = []
    completed = 0
    total = len(orders)

    logger.info(f"Fetching {total} order details...")

    with FuturesSession(session=humble_session, max_workers=max_workers) as retriever:
        order_futures = [
            retriever.get(f"{HUMBLE_ORDER_DETAILS_API}{order['gamekey']}?all_tpkds=true")
            for order in orders
        ]
        for future in as_completed(order_futures):
            try:
                resp = future.result()
                order_details.append(resp.json())
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                logger.warning(f"Failed to fetch order details: {e}")
            completed += 1
            print(f"\r{progress_bar(completed, total, prefix='Fetching orders: ')}", end="")

    print()  # Clear progress line
    return order_details


def main():
    """Main entry point for the application."""
    global stats

    # Reset statistics for this run
    stats = Statistics()

    # Show dry-run warning
    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")

    # Create a consistent session for Humble API use
    humble_session = cloudscraper.CloudScraper()
    humble_login(humble_session)
    logger.info("Successfully signed in on Humble.")

    try:
        orders = humble_session.get(HUMBLE_ORDERS_API, timeout=30).json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        logger.error(f"Failed to fetch orders from Humble Bundle: {e}")
        sys.exit(1)

    order_details = fetch_order_details(humble_session, orders)

    # Determine mode (from command line or interactive)
    if args.mode:
        desired_mode = str(args.mode)
        logger.info(f"Using mode {desired_mode} from command line")
    else:
        desired_mode = prompt_mode(order_details, humble_session)

    if desired_mode == "2":
        export_mode(humble_session, order_details)
        stats.print_summary()
        sys.exit(0)

    if desired_mode == "3":
        humble_chooser_mode(humble_session, order_details)
        stats.print_summary()
        sys.exit(0)

    # Auto-Redeem mode
    cls()
    steam_keys = list(find_dict_keys(order_details, "steam_app_id", True))
    steam_keys = filter_previous_keys(steam_keys)

    unrevealed_keys = []
    revealed_keys = []

    for key in steam_keys:
        if "redeemed_key_val" in key:
            revealed_keys.append(key)
        else:
            # Has not been revealed via Humble yet
            unrevealed_keys.append(key)

    logger.info(
        f"{len(steam_keys)} Steam keys total -- {len(revealed_keys)} revealed, {len(unrevealed_keys)} unrevealed"
    )

    # Handle command-line specified options or interactive prompts
    if args.reveal_keys:
        will_reveal_keys = True
        try_already_revealed = True
    else:
        will_reveal_keys = prompt_yes_no(
            "Would you like to redeem on Humble as-yet un-revealed Steam keys? "
            "(Revealing keys removes your ability to generate gift links for them)"
        )
        if will_reveal_keys:
            try_already_revealed = prompt_yes_no(
                "Would you like to attempt redeeming already-revealed keys as well?"
            )
        else:
            try_already_revealed = False

    # Determine which keys to process
    if will_reveal_keys:
        keys_to_redeem = steam_keys if try_already_revealed else unrevealed_keys
    else:
        keys_to_redeem = revealed_keys

    # Create backup if requested
    if args.backup and len(keys_to_redeem) > 0:
        logger.info("Creating backup before processing...")
        backup_path = create_backup(keys_to_redeem)
        logger.info(f"Backup saved to: {backup_path}")

    # Redeem keys
    redeem_steam_keys(
        humble_session,
        keys_to_redeem,
        dry_run=args.dry_run,
        skip_steam_check=args.no_steam_check
    )

    # Cleanup file handles
    for f in files:
        try:
            files[f].close()
        except Exception as e:
            logger.debug(f"Error closing file {f}: {e}")

    # Print session summary
    stats.print_summary()

    # Clean up session state file on successful completion
    if os.path.exists("session_state.json") and not args.dry_run:
        try:
            os.remove("session_state.json")
        except IOError:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        stats.print_summary()
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        stats.print_summary()
        sys.exit(1)
