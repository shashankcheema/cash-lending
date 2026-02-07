# Changelog

All notable changes to this project will be documented in this file.

## Unreleased
- Added Paytm-like support with `record_status` filtering (only `SUCCESS` rows processed).
- Added row-level validation with rejection breakdown buckets (counts only).
- Added `partial_record` quality flag handling with `accepted_partial_rows`.
- Added guardrail for low-quality batches via `MIN_ACCEPT_RATIO` (default `0.10`, configurable).
- Added JSON feeds ingestion endpoint with watermark-based idempotency and replay protection.
- Updated docs (README, Status, Architecture) to reflect current behavior.
