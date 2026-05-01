# syntax=docker/dockerfile:1
# =====================================================================
# chief_of_staff/browser_runner/Dockerfile
#
# Phase 4 — Playwright-based browser automation runner.
# Uses the official Microsoft Playwright Python image which already has
# Chromium + the playwright package installed.
# =====================================================================
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

COPY chief_of_staff/browser_runner/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

COPY chief_of_staff/browser_runner/ ./chief_of_staff/browser_runner/
COPY chief_of_staff/__init__.py ./chief_of_staff/

RUN mkdir -p /data/profiles
ENV BROWSER_PROFILES_DIR=/data/profiles

EXPOSE 8002

CMD ["uvicorn", "chief_of_staff.browser_runner.server:app", "--host", "0.0.0.0", "--port", "8002"]
