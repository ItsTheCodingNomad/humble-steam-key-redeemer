# Contributing to Humble Steam Key Redeemer

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Reporting Issues

If you encounter a bug or have a feature request:

1. Check existing issues to avoid duplicates
2. Create a new issue with:
   - Clear description of the problem or feature
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Python version and OS
   - Relevant log excerpts from `humble_redeemer.log`

## Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/humble-steam-key-redeemer.git
   cd humble-steam-key-redeemer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install python-Levenshtein  # Optional but recommended
   ```

3. Create a branch for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Testing Your Changes

Before submitting a pull request, test your changes thoroughly:

1. **Use dry-run mode** for safe testing:
   ```bash
   python humblesteamkeysredeemer.py --dry-run --verbose
   ```

2. **Test all modes** if your change affects core functionality:
   - Mode 1: Auto-redeem
   - Mode 2: Export
   - Mode 3: Humble Choice

3. **Check the logs** in `humble_redeemer.log` for any errors

## Code Style

- **Type hints**: Add type hints to function signatures
- **Docstrings**: Document all functions with clear descriptions
- **Error handling**: Use specific exception types, avoid bare `except:`
- **Logging**: Use the `logger` object, not `print()` for non-user output
- **Configuration**: Use the `config` object for customizable values
- **Statistics**: Update the `stats` object for tracked metrics

### Example

```python
def redeem_key(session: requests.Session, key: str, dry_run: bool = False) -> int:
    """Redeem a key on a service.

    Args:
        session: Authenticated HTTP session
        key: The key to redeem
        dry_run: If True, don't actually redeem

    Returns:
        Error code (0 = success)
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would redeem key: {key[:5]}*****")
        return 0

    try:
        response = session.post(URL, data={"key": key}, timeout=30)
        return process_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        return -1
```

## Pull Request Process

1. **Update documentation** if your changes affect usage
2. **Update CHANGELOG.md** with your changes
3. **Test thoroughly** using dry-run mode
4. **Write a clear commit message** describing the change and why
5. **Submit a pull request** with:
   - Clear description of the changes
   - Any related issue numbers
   - Screenshots if UI-related

## Security Considerations

This project handles sensitive data (credentials and keys):

- **Never commit** cookie files (`.humblecookies`, `.steamcookies`)
- **Never commit** CSV output files (may contain keys)
- **Never log** sensitive data at INFO level or above
- **Always use** HTTPS URLs for API calls
- **Validate** all user inputs

## Priority Areas for Contribution

- Additional platform support (GOG, Epic, etc.)
- Unit tests
- Better fuzzy matching algorithm
- GUI interface
- Internationalization (i18n)
- Dockerization

## Questions?

Feel free to open a discussion issue for any questions about contributing.
