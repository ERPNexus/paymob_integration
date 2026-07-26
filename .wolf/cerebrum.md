# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-07-26

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- Repository commitments should include a dedicated Conventional Commits rule for consistency.

## Key Learnings

- **Project:** paymob_integration
- **Description:** Seamless integration for paymob with ERPNext
- Country, currency, and mode jointly identify Paymob credentials and integration IDs; callers must
  supply all three to avoid selecting a regional account by row order.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-07-26] Commit OpenWolf's shared protocol, configuration, identity, and hooks; ignore its
  generated session state and visual-review output to keep repository history useful and clean.
