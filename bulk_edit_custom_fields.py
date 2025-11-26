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
import requests
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from jira import JIRA
from jira.exceptions import JIRAError
from jira.resources import Issue

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


def search_issues_v3(jira: JIRA, jql: str, fields: List[str], max_results: Optional[int] = None) -> List[Any]:
    """
    Search for issues using the new Jira API v3 /search/jql endpoint.

    This function bypasses the jira library's search_issues method which uses
    the deprecated /search endpoint, and instead uses the new /search/jql endpoint.

    Args:
        jira: JIRA client instance (used for authentication and issue objects)
        jql: JQL query string
        fields: List of field names to retrieve
        max_results: Maximum number of results to return (None for all)

    Returns:
        List of issue objects
    """
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    url = f"{JIRA_URL}/rest/api/3/search/jql"

    all_issues = []
    seen_keys = set()  # Track issue keys to avoid duplicates
    start_at = 0
    page_size = 100  # Jira's max per request

    # First request to get total count
    logger.info("Fetching issues from Jira...")

    while True:
        # Determine how many to fetch this batch
        remaining = None
        if max_results:
            remaining = max_results - len(all_issues)
            if remaining <= 0:
                break
            page_size = min(100, remaining)

        params = {
            'jql': jql,
            'startAt': start_at,
            'maxResults': page_size,
            'fields': ','.join(fields)
        }

        logger.info(f"Fetching batch: startAt={start_at}, maxResults={page_size}")
        response = requests.get(url, auth=auth, params=params)

        if response.status_code != 200:
            raise JIRAError(
                f"Search failed: HTTP {response.status_code}\n"
                f"URL: {response.url}\n"
                f"Response: {response.text}"
            )

        data = response.json()
        issues_data = data.get('issues', [])
        total = data.get('total', 0)

        # Log total on first request (if available)
        if start_at == 0:
            if total > 0:
                logger.info(f"Total issues matching query: {total}")
            else:
                logger.info(f"Note: Total count not available from API, will fetch until no more results")
            if max_results:
                logger.info(f"Will process maximum of {max_results} issues")

        # Process issues from response data directly (avoid redundant API calls)
        duplicates_in_batch = 0
        for issue_data in issues_data:
            issue_key = issue_data['key']

            # Check for duplicates
            if issue_key in seen_keys:
                logger.warning(f"Duplicate issue detected: {issue_key} at startAt={start_at}")
                duplicates_in_batch += 1
                continue

            # Create issue object from the response data using jira library's resource
            # This avoids making separate API calls for each issue
            issue = Issue(jira._options, jira._session, raw=issue_data)
            all_issues.append(issue)
            seen_keys.add(issue_key)

        if duplicates_in_batch > 0:
            logger.warning(f"Skipped {duplicates_in_batch} duplicate issues in this batch")

        fetched_count = len(all_issues)
        if total > 0:
            logger.info(f"Fetched {len(issues_data)} issues in this batch (total: {fetched_count}/{total})")
        else:
            logger.info(f"Fetched {len(issues_data)} issues in this batch (total so far: {fetched_count})")

        # Stop conditions
        start_at += len(issues_data)

        # Primary stop condition: no more issues returned
        if len(issues_data) == 0:
            logger.info("No more issues to fetch")
            break

        # Secondary stop condition: only if total is reliable (> 0) and we've reached it
        if total > 0 and start_at >= total:
            logger.info("Reached end of results")
            break

        # Stop if we've reached the max_results limit
        if max_results and fetched_count >= max_results:
            logger.info(f"Reached max_results limit of {max_results}")
            break

    logger.info(f"Finished fetching. Total issues retrieved: {len(all_issues)}")
    return all_issues


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
        # Use API v3 (v2 has been deprecated and removed)
        options = {
            'server': JIRA_URL,
            'rest_api_version': '3'
        }
        jira = JIRA(
            options=options,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        logger.info("Successfully connected to Jira (using API v3)")
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

        # Search for issues using the new v3 endpoint
        logger.info(f"Executing JQL query: {JQL_QUERY}")
        issues = search_issues_v3(
            jira,
            JQL_QUERY,
            fields=[SOURCE_FIELD, TARGET_FIELD, 'summary'],
            max_results=max_results
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

        logger.info("")
        logger.info("=" * 80)
        logger.info("STARTING ISSUE PROCESSING")
        logger.info("=" * 80)

        progress_interval = 10 if total_issues < 100 else 25

        for idx, issue in enumerate(issues, 1):
            logger.info(f"\n[{idx}/{total_issues}] Processing: {issue.key} - {issue.fields.summary}")
            result = process_issue(jira, issue, dry_run)

            results['processed'] += 1
            if result['success']:
                if result['updated']:
                    results['updated'] += 1
                else:
                    results['skipped'] += 1
            else:
                results['errors'] += 1

            # Show progress summary periodically
            if idx % progress_interval == 0 or idx == total_issues:
                logger.info("")
                logger.info("-" * 80)
                logger.info(f"PROGRESS UPDATE: {idx}/{total_issues} issues processed")
                logger.info(f"  Updated: {results['updated']}, Skipped: {results['skipped']}, Errors: {results['errors']}")
                logger.info("-" * 80)

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
        help='Maximum number of issues to process (useful for testing or batch processing large numbers)'
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
