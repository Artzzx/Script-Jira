# Script-Jira

Collection of automation scripts for Jira operations.

## Bulk Edit Custom Fields Script

This script performs bulk editing of Jira issues by copying validated values from one custom field to another.

### Functionality

The script:
- Searches for issues matching a specific JQL query
- Extracts values from `customfield_10213` (Numéro de soumission[Short text])
- Validates values against the pattern `^S-\d{5,6}$`
- Copies valid values to `customfield_10683` (Liste Numéro de soumission[Labels])
- Only processes values that match the validation pattern

### JQL Query

```
project = es
AND "Numéro de soumission[Short text]" !~ "S-"
AND "Liste Numéro de soumission[Labels]" is empty
AND assignee != 5f6aaf8fad3484006a8038e1
```

### Prerequisites

- Python 3.7 or higher
- Jira account with appropriate permissions
- API token for Jira authentication

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd Script-Jira
   ```

2. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your actual Jira credentials
   ```

### Configuration

Edit the `.env` file with your Jira credentials:

```env
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token-here
```

To generate a Jira API token:
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label and copy the token
4. Paste it into your `.env` file

### Usage

#### Dry Run (Recommended First)

Always run in dry-run mode first to see what changes would be made:

```bash
python bulk_edit_custom_fields.py --dry-run
```

#### Test with Limited Results

Process only a few issues for testing:

```bash
python bulk_edit_custom_fields.py --dry-run --max-results 5
```

#### Live Update

Once you've verified the dry-run results, run the actual update:

```bash
python bulk_edit_custom_fields.py
```

You'll be prompted to confirm before any changes are made.

### Command Line Options

- `--dry-run`: Run without making actual updates (shows what would be changed)
- `--max-results N`: Limit processing to N issues (useful for testing)

### Output

The script logs all operations to:
- Console (stdout)
- `bulk_edit.log` file

### Validation Rules

Values are only copied if they match the pattern `^S-\d{5,6}$`:
- Must start with "S-"
- Followed by 5 or 6 digits
- Examples: `S-12345`, `S-123456`

Invalid values are skipped and logged.

### Error Handling

The script handles:
- Missing or empty source field values
- Values that don't match the validation pattern
- Issues where the target field already contains values
- Jira API errors
- Network connection issues

All errors are logged with details for troubleshooting.

### Safety Features

1. **Dry-run mode**: Test before making changes
2. **Confirmation prompt**: Required for live updates
3. **Comprehensive logging**: Track all operations
4. **Validation**: Only valid values are copied
5. **Error recovery**: Continues processing if individual issues fail

### Example Output

```
2025-11-26 10:00:00 - INFO - Starting Jira Bulk Edit Script
2025-11-26 10:00:00 - INFO - Mode: DRY RUN
2025-11-26 10:00:01 - INFO - Found 15 issues to process

Processing 1/15: ES-123 - Sample Issue Title
ES-123: [DRY RUN] Would update customfield_10683 with: ['S-12345']

Processing 2/15: ES-124 - Another Issue
ES-124: Value 'invalid' does not match pattern ^S-\d{5,6}$

...

SUMMARY
Total issues processed: 15
Successfully updated: 12
Skipped: 2
Errors: 1
```

### Troubleshooting

**Authentication Issues**
- Verify your API token is correct
- Ensure your email matches your Jira account
- Check that your account has permission to edit the issues

**Field Not Found**
- Verify the custom field IDs are correct for your Jira instance
- Check that the fields exist in the project

**Pattern Validation Failures**
- Review the values in the source field
- Ensure they match the format `S-12345` or `S-123456`

### License

This project is provided as-is for internal use.