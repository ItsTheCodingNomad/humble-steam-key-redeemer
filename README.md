# Humble Steam Key Redeemer

Python script to extract all Humble Bundle keys and redeem them on Steam automatically.

This is primarily designed to be a set-it-and-forget-it tool that maximizes successful entry of keys into Steam, assuring that no Steam game goes unredeemed.

## Features

- **Auto-Redeem Mode**: Automatically extract and redeem Steam keys from your Humble Bundle account
- **Export Mode**: Export your Humble Bundle keys to CSV for manual management
- **Humble Choice Manager**: Select and redeem games from your Humble Choice subscriptions
- **Smart Ownership Detection**: Uses fuzzy matching to detect games you already own on Steam
- **Rate Limit Handling**: Automatically waits and retries when Steam's rate limit is hit
- **Session Persistence**: Saves login sessions to avoid repeated authentication
- **Dry-Run Mode**: Preview what would happen without making any changes
- **Progress Tracking**: Visual progress bars for long operations
- **Detailed Logging**: Comprehensive logs for debugging and auditing
- **Configuration File**: Customize settings via `config.ini`
- **Backup Support**: Create backups of keys before revealing them

## Installation

### Requirements

- Python 3.6 or higher
- A Humble Bundle account with purchased games
- A Steam account

### Dependencies

Install the required dependencies:

```bash
pip install -r requirements.txt
```

**Required packages:**
- `steam`: Steam authentication and API interaction
- `fuzzywuzzy`: Fuzzy string matching for game ownership detection
- `requests`: HTTP requests
- `requests-futures`: Asynchronous HTTP requests
- `cloudscraper`: Bypass Cloudflare protection

**Optional (recommended for performance):**
```bash
pip install python-Levenshtein
```

## Usage

### Basic Usage

```bash
python humblesteamkeysredeemer.py
```

This will start the interactive mode where you can choose from:
1. **Auto-Redeem** - Automatically redeem keys on Steam
2. **Export keys** - Export keys to CSV file
3. **Humble Choice chooser** - Manage Humble Choice selections

### Command-Line Options

```bash
python humblesteamkeysredeemer.py [OPTIONS]

Options:
  --mode, -m {1,2,3}    Operation mode: 1=Auto-Redeem, 2=Export, 3=Humble Choice
  --dry-run, -n         Preview actions without making changes
  --verbose, -v         Enable verbose/debug output
  --config, -c FILE     Path to configuration file (default: config.ini)
  --reveal-keys         Automatically reveal unrevealed keys
  --export-revealed     Export only revealed keys (mode 2)
  --export-unrevealed   Export only unrevealed keys (mode 2)
  --steam-only          Process only Steam keys
  --backup, -b          Create backup before revealing keys
  --resume, -r FILE     Resume from a previous session file
  --no-steam-check      Skip Steam ownership check
```

### Examples

```bash
# Run in auto-redeem mode
python humblesteamkeysredeemer.py --mode 1

# Preview what would be redeemed (dry run)
python humblesteamkeysredeemer.py --mode 1 --dry-run

# Export revealed Steam keys only
python humblesteamkeysredeemer.py --mode 2 --export-revealed --steam-only

# Auto-redeem with backup and verbose logging
python humblesteamkeysredeemer.py --mode 1 --backup --verbose

# Skip Steam ownership check (faster but may fail on owned games)
python humblesteamkeysredeemer.py --mode 1 --no-steam-check
```

### Windows Quick Start

Double-click `run_redeemer.bat` to automatically install dependencies and run the script.

## Configuration

The script supports an optional `config.ini` file for customizing behavior:

```ini
[humble]
cookie_file = .humblecookies

[steam]
cookie_file = .steamcookies
rate_limit_keys_per_hour = 50
rate_limit_failed_per_hour = 10

[output]
redeemed_file = redeemed.csv
owned_file = already_owned.csv
errored_file = errored.csv
export_prefix = humble_export_
backup_dir = backups

[settings]
fuzzy_match_threshold = 70
max_concurrent_requests = 30
retry_attempts = 3
retry_delay_seconds = 2
```

## Output Files

The script generates several output files:

| File | Description |
|------|-------------|
| `redeemed.csv` | Successfully redeemed keys |
| `already_owned.csv` | Keys for games already owned on Steam |
| `errored.csv` | Keys that failed to redeem |
| `humble_export_*.csv` | Export mode output (timestamped) |
| `humble_redeemer.log` | Detailed operation log |
| `backups/*.json` | Key backups (when using --backup) |

## Session Management

The script saves session cookies to avoid repeated logins:
- `.humblecookies` - Humble Bundle session
- `.steamcookies` - Steam session

To log out or switch accounts, delete the respective cookie file.

## Rate Limiting

Steam has rate limits on key redemption:
- **50 successful keys per hour**
- **10 failed keys per hour**

The script automatically:
1. Checks ownership before attempting redemption
2. Uses fuzzy matching to detect potentially owned games
3. Waits and retries when rate limited

## Troubleshooting

### Common Issues

**"TOS update required"**
- Sign in to Humble Bundle in your browser and accept any updated terms

**"Cloudflare protection"**
- The script uses cloudscraper to bypass this, but it may occasionally fail
- Try again later or update cloudscraper: `pip install --upgrade cloudscraper`

**"Rate limit exceeded"**
- Wait an hour from your first key redemption attempt
- The script will automatically wait and retry

**Session expired**
- Delete `.humblecookies` or `.steamcookies` and log in again

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
python humblesteamkeysredeemer.py --verbose
```

Check `humble_redeemer.log` for detailed operation logs.

## Steam Error Codes

| Code | Description |
|------|-------------|
| 9 | Already owned |
| 13 | Region locked |
| 14 | Invalid key |
| 15 | Already activated by another account |
| 24 | Requires base game |
| 36 | PlayStation requirement |
| 50 | Wallet/Gift card code |
| 53 | Rate limited |

## Security Notes

- Session cookies are stored locally in pickle files
- No passwords are stored - only session tokens
- Cookie files are excluded from git via `.gitignore`
- Supports Steam Guard and Humble Guard 2FA

## Contributing

Feel free to submit issues or pull requests on GitHub.

## License

This project is provided as-is for personal use.

## Acknowledgments

- Original script by FailSpy
- Uses [ValvePython/steam](https://github.com/ValvePython/steam) for Steam authentication
- Uses [seatgeek/fuzzywuzzy](https://github.com/seatgeek/fuzzywuzzy) for fuzzy matching
