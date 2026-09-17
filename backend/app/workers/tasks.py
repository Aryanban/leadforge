from app.workers import celery_app
from app.scraper.maps_scraper import scrape_google_maps
from app.enricher.email_finder import crawl_website_for_contacts
from app.verifier.smtp_verifier import verify_email_smtp
import asyncio
from sqlalchemy.orm import Session
from app.database import engine
from app.models.business import Business
from app.models.contact import Contact

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
