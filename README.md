# Gretel PII Transform Pre-Commit Hook
This project is an example of using Gretel's PII Transform tool paired with Git Hooks to automatically detect csv files with potential PII that are being commited to git by mistake. The tool will then transform and replace the original CSV files to ensure PII isn't linked

## First Clone
When you first clone this repository, run the following command:
`cp pre-commit .git/hooks`

Pre-Commit Hooks aren't tracked in git, so if an update is made to the hook you'll need to copy the hook again.
