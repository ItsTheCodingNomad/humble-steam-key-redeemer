# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - Major Enhancement Update

### Added
- **Command-line interface** with `argparse`
  - `--mode` / `-m` - Select operation mode (1=Auto-Redeem, 2=Export, 3=Humble Choice)
  - `--dry-run` / `-n` - Preview actions without making changes
  - `--verbose` / `-v` - Enable debug output
  - `--config` / `-c` - Specify custom configuration file
  - `--reveal-keys` - Automatically reveal unrevealed keys
  - `--export-revealed` / `--export-unrevealed` - Control export behavior
  - `--steam-only` - Process only Steam keys
  - `--backup` / `-b` - Create backup before revealing keys
  - `--resume` / `-r` - Resume from a previous session file
  - `--no-steam-check` - Skip Steam ownership check
- **Configuration file support** via `config.ini`
  - Customizable fuzzy match threshold
  - Configurable output file paths
  - Adjustable concurrent request limits
  - Retry settings
- **Proper Python logging system**
  - File handler with timestamps (`humble_redeemer.log`)
  - Console handler with configurable verbosity
  - Structured log levels (DEBUG, INFO, WARNING, ERROR)
- **Dry-run mode** for safe testing without making changes
- **Key backup functionality** to save keys before revealing
- **Session resume capability** with state persistence
- **Progress bars** for long operations:
  - Order detail fetching
  - Ownership checking
  - Key redemption
- **Session statistics** summary at completion:
  - Keys found, redeemed, already owned, failed, skipped
  - Rate limit waits
  - Error counts
  - Total duration
- **Retry logic framework** with exponential backoff decorator
- **`config.example.ini`** - Reference configuration file
- **`CHANGELOG.md`** - Version history documentation
- **`CONTRIBUTING.md`** - Contributor guidelines

### Changed
- **Comprehensive type hints** added throughout the codebase
- **Docstrings** added to all functions
- **Steam error messages** extracted to constant dictionary for maintainability
- **Refactored main execution** into proper `main()` function
- **Proper entry point** with `if __name__ == "__main__"`
- **README** completely rewritten with:
  - Feature list
  - Command-line option reference
  - Usage examples
  - Configuration guide
  - Troubleshooting section
  - Steam error codes table
- **`.gitignore`** updated for new generated files (logs, backups, session state)

### Fixed
- **Error handling** - Replaced all bare `except:` clauses with specific exception types
- **Network timeouts** - All HTTP requests now have timeouts (30-60 seconds)
- **Graceful interruption** - Keyboard interrupts now properly display summary
- **Cookie file errors** - Specific handling for corrupted, missing, or permission-denied cookie files
- **JSON decode errors** - Proper handling of invalid API responses
- **File handle cleanup** - More robust cleanup on exit

### Security
- Explicit exception types prevent silent failures that could mask security issues
- Network request timeouts prevent hanging on malicious/slow responses
- Config file excluded from git to prevent accidental commit of paths

## [Previous] - CloudScraper Integration

### Changed
- Switched to CloudScraper for Humble Bundle to bypass Cloudflare protection

## [Previous] - Initial Version

### Added
- Humble Bundle authentication with session persistence
- Steam authentication via ValvePython/steam library
- Auto-redeem mode for Steam keys
- Export mode for CSV output
- Humble Choice selection mode
- Fuzzy matching for ownership detection
- Rate limit handling with retry logic
