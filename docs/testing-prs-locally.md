# Testing Pull Requests Locally

This guide explains how to test pull requests locally while preserving your current working changes.

## Prerequisites

- You have uncommitted local changes that you don't want to lose
- You want to test a specific PR without affecting your current work

## Method 1: Create a Test Branch (Recommended)

This method creates a separate branch for testing the PR while keeping your changes safe.

### Step 1: Check Current Status
```bash
git status
```

### Step 2: Create a Test Branch
```bash
git checkout -b test-pr-[PR-NUMBER]
```
Replace `[PR-NUMBER]` with the actual PR number (e.g., `test-pr-47`).

### Step 3: Fetch the PR
```bash
git fetch origin pull/[PR-NUMBER]/head:pr-[PR-NUMBER]
```
Replace `[PR-NUMBER]` with the actual PR number (e.g., `git fetch origin pull/47/head:pr-47`).

### Step 4: Merge PR Changes
```bash
git merge pr-[PR-NUMBER]
```
Replace `[PR-NUMBER]` with the actual PR number (e.g., `git merge pr-47`).

### Step 5: Resolve Conflicts (if any)
If there are merge conflicts:
1. Open the conflicted files in your editor
2. Look for conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
3. Choose which changes to keep (usually the PR changes for testing)
4. Remove the conflict markers
5. Stage the resolved files: `git add <file>`
6. Complete the merge: `git commit`

### Step 6: Test the Changes
Now you can test the PR changes in your test branch.

### Step 7: Return to Your Work
When done testing:
```bash
git checkout main
# Your original changes are still there, uncommitted
```

### Step 8: Clean Up (Optional)
To remove the test branch when done:
```bash
git branch -D test-pr-[PR-NUMBER]
git branch -D pr-[PR-NUMBER]
```

## Method 2: Stash and Restore (Alternative)

If you prefer to temporarily save your changes:

### Step 1: Stash Your Changes
```bash
git stash push -m "Testing PR [PR-NUMBER]"
```

### Step 2: Fetch and Checkout PR
```bash
git fetch origin pull/[PR-NUMBER]/head:pr-[PR-NUMBER]
git checkout pr-[PR-NUMBER]
```

### Step 3: Test the Changes
Test the PR as needed.

### Step 4: Return to Your Work
```bash
git checkout main
git stash pop
```

## Method 3: Cherry-pick Specific Changes

If you only want to test specific files from the PR:

### Step 1: Create Test Branch
```bash
git checkout -b test-pr-[PR-NUMBER]
```

### Step 2: Cherry-pick Specific Commits
```bash
git cherry-pick [COMMIT-HASH]
```

### Step 3: Test and Clean Up
Test the changes, then return to your work branch.

## Troubleshooting

### Conflict Resolution Tips
- **Package.json conflicts**: Usually accept the PR version for testing
- **Code conflicts**: Review both versions and choose the appropriate changes
- **Configuration conflicts**: Be careful with config changes that might affect your environment

### If You Accidentally Commit
If you accidentally commit your test changes:
```bash
git reset --soft HEAD~1  # Undo the commit, keep changes staged
git reset HEAD           # Unstage the changes
```

### If You Need to Start Over
```bash
git checkout main
git branch -D test-pr-[PR-NUMBER]
git branch -D pr-[PR-NUMBER]
```

## Best Practices

1. **Always create a test branch** - Never test PRs directly on your working branch
2. **Document what you're testing** - Use descriptive branch names
3. **Clean up after testing** - Remove test branches when done
4. **Backup important changes** - Consider creating a backup branch for critical work
5. **Test thoroughly** - Make sure the PR works as expected before approving

## Example Workflow

```bash
# Check current status
git status

# Create test branch
git checkout -b test-pr-47

# Fetch and merge PR
git fetch origin pull/47/head:pr-47
git merge pr-47

# Resolve any conflicts, then test
# ... test the changes ...

# Return to work
git checkout main

# Clean up
git branch -D test-pr-47
git branch -D pr-47
```

## Notes

- This guide assumes you're working on the `main` branch
- Replace `[PR-NUMBER]` with the actual PR number throughout
- The test branch approach is recommended as it's the safest method
- Always review PR changes before merging them into your test branch
