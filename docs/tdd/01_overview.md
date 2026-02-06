# Technical Design Document (TDD) — Cash-Flow Lending Platform

## Title
Cash-Flow Based Lending Platform (Pre-AA / GSTN / UPI) — Core Underwriting & Monitoring System

## Status
Draft v1

## Authors / Owners
- Product Owner: TBD
- Engineering Owner: TBD
- Risk/Policy Owner: TBD

## Last Updated
2026-02-04

## Data Storage Policy (RBI / AA Minimization)
**No Raw Subject Data at Rest**
- Raw transactions, bank statements, and payer identifiers must never be persisted.
- Only aggregated features and analytic or risk output packets are stored.
- Temporary input handling must be ephemeral with TTL and purge enforced.
- Audit logs store metadata only and must exclude PII or raw payloads.

## Problem Statement
AA/GSTN/UPI/OCEN integrations can take months due to partner onboarding, regulatory constraints, and access approvals. Engineering velocity should not be blocked by external dependencies.

We need to build a platform that can:
- Ingest transaction-like data from non‑regulated sources (CSV, exports, bank-statement-like feeds, synthetic data)
- Produce cash‑flow health analytics, fraud or mule flags, and dynamic credit limit (Drawing Power) outputs
- Simulate loan lifecycle and collections behavior to validate risk and repayment strategies
- Provide NBFC-ready dashboards and APIs

Later, regulated data rails (AA, GSTN, UPI PSP) should be integrated via adapters without rewriting core logic.

## Goals
1. Data‑agnostic underwriting brain: feature computation, health scoring, EWS, DP, fraud rules.
2. Pluggable ingestion adapters: CSV or JSON or statement parsing now; AA or GST or UPI later.
3. Explainability‑first outputs: every score, limit, and flag includes reasons.
4. Simulation‑first validation: loan and collections simulator for evaluation without production rails.
5. APIs and dashboards supporting subject and portfolio views.

## Non‑Goals (v1)
- Production‑grade OCEN loan origination and disbursement.
- Full KYC and eSign workflows.
- Bureau integrations.
- Fully automated model-based underwriting beyond deterministic DP and rule engines.
- Real‑time streaming scale (batch and near‑real‑time later).
