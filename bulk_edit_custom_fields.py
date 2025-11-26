#!/usr/bin/env python3
"""
Bulk Edit Jira Custom Fields Script

This script searches for Jira issues matching a specific JQL query and copies
validated values from customfield_10213 to customfield_10683 (list field).

Only values matching the regex pattern ^S-\d{5,6}$ are copied.
"""

import os
import re
import sys
import logging
from typing import List, Optional
from dotenv import load_dotenv
from jira import JIRA
from jira.exceptions import JIRAError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bulk_edit.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
JIRA_URL = os.getenv('JIRA_URL')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')

# Field IDs
SOURCE_FIELD = 'customfield_10213'  # Numéro de soumission[Short text]
TARGET_FIELD = 'customfield_10683'  # Liste Numéro de soumission[Labels]

# Validation regex pattern
VALIDATION_PATTERN = re.compile(r'^S-\d{5,6}$')

# JQL Query
JQL_QUERY = '''
project = es
AND "Numéro de soumission[Short text]" !~ "S-"
AND "Liste Numéro de soumission[Labels]" is empty
AND assignee != 5f6aaf8fad3484006a8038e1
'''.strip()


def validate_value(value: str) -> bool:
    """
    Validate that a value matches the required pattern.

    Args:
        value: The value to validate

    Returns:
        True if the value matches the pattern ^S-\d{5,6}$, False otherwise
    """
    if not value:
        return False
    return bool(VALIDATION_PATTERN.match(value.strip()))


def connect_to_jira() -> JIRA:
    """
    Establish connection to Jira.

    Returns:
        JIRA client instance

    Raises:
        ValueError: If required credentials are missing
        JIRAError: If connection fails
    """
    if not all([JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
        raise ValueError(
            "Missing required credentials. Please set JIRA_URL, JIRA_EMAIL, "
            "and JIRA_API_TOKEN in your .env file"
        )

    logger.info(f"Connecting to Jira at {JIRA_URL}...")
    try:
        jira = JIRA(
            server=JIRA_URL,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        logger.info("Successfully connected to Jira")
        return jira
    except JIRAError as e:
        logger.error(f"Failed to connect to Jira: {e}")
        raise


def process_issue(jira: JIRA, issue, dry_run: bool = False) -> dict:
    """
    Process a single issue by copying validated value from source to target field.

    Args:
        jira: JIRA client instance
        issue: The Jira issue to process
        dry_run: If True, don't actually update the issue

    Returns:
        Dictionary with processing results
    """
    issue_key = issue.key
    result = {
        'key': issue_key,
        'success': False,
        'message': '',
        'source_value': None,
        'updated': False
    }

    try:
        # Get source field value
        source_value = getattr(issue.fields, SOURCE_FIELD, None)
        result['source_value'] = source_value

        if not source_value:
            result['message'] = f"No value in {SOURCE_FIELD}"
            logger.info(f"{issue_key}: {result['message']}")
            return result

        # Clean and validate the value
        cleaned_value = source_value.strip()

        if not validate_value(cleaned_value):
            result['message'] = f"Value '{cleaned_value}' does not match pattern ^S-\\d{{5,6}}$"
            logger.warning(f"{issue_key}: {result['message']}")
            return result

        # Get current target field value (should be empty based on JQL, but check anyway)
        current_target = getattr(issue.fields, TARGET_FIELD, None)

        # Prepare the update - target field is a list
        # For Labels type fields, we need to pass a list of strings
        new_value = [cleaned_value]

        if current_target:
            # If there's already a value, we might want to append instead of replace
            # But based on the JQL query, this should be empty
            logger.warning(f"{issue_key}: Target field not empty: {current_target}")
            if cleaned_value not in current_target:
                new_value = current_target + [cleaned_value]
            else:
                result['message'] = f"Value '{cleaned_value}' already exists in target field"
                logger.info(f"{issue_key}: {result['message']}")
                result['success'] = True
                return result

        if dry_run:
            result['message'] = f"[DRY RUN] Would update {TARGET_FIELD} with: {new_value}"
            result['success'] = True
            logger.info(f"{issue_key}: {result['message']}")
            return result

        # Update the issue
        issue.update(fields={TARGET_FIELD: new_value})

        result['success'] = True
        result['updated'] = True
        result['message'] = f"Successfully updated {TARGET_FIELD} with '{cleaned_value}'"
        logger.info(f"{issue_key}: {result['message']}")

    except JIRAError as e:
        result['message'] = f"Jira API error: {str(e)}"
        logger.error(f"{issue_key}: {result['message']}")
    except Exception as e:
        result['message'] = f"Unexpected error: {str(e)}"
        logger.error(f"{issue_key}: {result['message']}", exc_info=True)

    return result


def main(dry_run: bool = False, max_results: Optional[int] = None):
    """
    Main function to process all matching issues.

    Args:
        dry_run: If True, don't actually update issues
        max_results: Maximum number of issues to process (None for all)
    """
    logger.info("=" * 80)
    logger.info("Starting Jira Bulk Edit Script")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")
    logger.info("=" * 80)

    try:
        # Connect to Jira
        jira = connect_to_jira()

        # Search for issues
        logger.info(f"Executing JQL query: {JQL_QUERY}")
        issues = jira.search_issues(
            JQL_QUERY,
            maxResults=max_results if max_results else False,
            fields=[SOURCE_FIELD, TARGET_FIELD, 'summary']
        )

        total_issues = len(issues)
        logger.info(f"Found {total_issues} issues to process")

        if total_issues == 0:
            logger.info("No issues found matching the JQL query")
            return

        # Process each issue
        results = {
            'processed': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }

        for idx, issue in enumerate(issues, 1):
            logger.info(f"\nProcessing {idx}/{total_issues}: {issue.key} - {issue.fields.summary}")
            result = process_issue(jira, issue, dry_run)

            results['processed'] += 1
            if result['success']:
                if result['updated']:
                    results['updated'] += 1
                else:
                    results['skipped'] += 1
            else:
                results['errors'] += 1

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total issues processed: {results['processed']}")
        logger.info(f"Successfully updated: {results['updated']}")
        logger.info(f"Skipped: {results['skipped']}")
        logger.info(f"Errors: {results['errors']}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Bulk edit Jira custom fields based on JQL query'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in dry-run mode (no actual updates)'
    )
    parser.add_argument(
        '--max-results',
        type=int,
        help='Maximum number of issues to process (for testing)'
    )

    args = parser.parse_args()

    # Always run in dry-run mode first if not explicitly set
    if not args.dry_run:
        confirm = input(
            "\n⚠️  WARNING: You are about to update Jira issues in LIVE mode.\n"
            "Are you sure you want to continue? (yes/no): "
        )
        if confirm.lower() != 'yes':
            logger.info("Operation cancelled by user")
            sys.exit(0)

    main(dry_run=args.dry_run, max_results=args.max_results)
