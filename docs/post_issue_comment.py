#!/usr/bin/env python3
"""
Post research findings to GitHub Issue #10
Requires GITHUB_TOKEN environment variable or .git-credentials file
"""

import os
import sys
import json
import subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

def get_github_token():
    """Try to get GitHub token from various sources."""
    # Try environment variable first
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    
    # Try to extract from git credential helper
    try:
        result = subprocess.run(
            ['git', 'config', '--get', 'credential.helper'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            # Try to get token from git credential helper
            result = subprocess.run(
                ['git', 'credential', 'fill'],
                input='protocol=https\nhost=github.com\n\n',
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('password='):
                        return line.split('=', 1)[1].strip()
    except Exception:
        pass
    
    return None

def post_comment(owner, repo, issue_number, comment_file):
    """Post comment to GitHub issue."""
    if requests is None:
        print("❌ requests library not installed")
        print("Install it with: pip install requests")
        return False
    
    token = get_github_token()
    if not token:
        print("❌ Could not find GitHub token")
        print("\nTo post the comment, please use one of these methods:")
        print(f"1. gh issue comment {issue_number} --body-file {comment_file}")
        print(f"2. Manually copy content from {comment_file} to:")
        print(f"   https://github.com/{owner}/{repo}/issues/{issue_number}")
        return False
    
    # Read comment body
    with open(comment_file, 'r') as f:
        comment_body = f.read()
    
    # Post to GitHub API
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    data = {'body': comment_body}
    
    print(f"Posting research findings to Issue #{issue_number}...")
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        result = response.json()
        print(f"✅ Comment posted successfully!")
        print(f"View at: {result['html_url']}")
        return True
    else:
        print(f"❌ Failed to post comment (status {response.status_code})")
        print(f"Response: {response.text}")
        return False

if __name__ == '__main__':
    owner = 'shyndman'
    repo = 'generative-supply'
    issue_number = 10
    comment_file = Path(__file__).parent / 'telegram-image-display-research.md'
    
    success = post_comment(owner, repo, issue_number, str(comment_file))
    sys.exit(0 if success else 1)
