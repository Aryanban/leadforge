from app.workers import celery_app
from app.scraper.maps_scraper import scrape_google_maps
from app.enricher.email_finder import crawl_website_for_contacts
from app.verifier.smtp_verifier import verify_email_smtp
import asyncio
from sqlalchemy.orm import Session
from app.database import engine
from app.models.business import Business
from app.models.contact import Contact

from app.workers.beat_schedule import BEAT_SCHEDULE

celery_app.conf.beat_schedule = BEAT_SCHEDULE


@celery_app.task
def poll_replies_task():
    """Periodic IMAP sweep of every active mailbox (Celery deployment)."""
    from app.campaigns.reply_poller import poll_all_mailboxes
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(poll_all_mailboxes())
    finally:
        loop.close()

@celery_app.task
def run_scrape_task(query: str, max_results: int):
    # Run async function in sync context
    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(scrape_google_maps(query, max_results))
    finally:
        loop.close()
    return results

@celery_app.task
def enrich_and_verify_business(business_id: int, website: str):
    loop = asyncio.new_event_loop()
    try:
        crawled = loop.run_until_complete(crawl_website_for_contacts(website))
    finally:
        loop.close()

    emails = crawled.get("emails", [])

    valid_emails = []
    for email in emails:
        is_valid, status = verify_email_smtp(email)
        if is_valid:
            valid_emails.append(email)

    return valid_emails
