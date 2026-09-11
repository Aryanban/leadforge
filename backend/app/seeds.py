import logging
from sqlalchemy import select
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep
from app.models.mailbox import Mailbox
from app.models.scrape_job import ScrapeJob
from datetime import datetime

logger = logging.getLogger(__name__)

SAMPLE_BUSINESSES = [
    {
        "name": "Balaji Properties & Developers",
        "phone": "+91 98112 34567",
        "website": "https://balajiproperties.example.in",
        "address": "Shop 14, Main Market, Sector 8, Rohini, New Delhi 110085",
        "rating": 4.8,
        "reviews_count": 84,
        "industry": "Real Estate Agency",
        "contacts": [
            {
                "first_name": "Rajesh",
                "last_name": "Sharma",
                "title": "Principal Broker",
                "email": "rajesh@balajiproperties.example.in",
                "phone": "+91 98112 34567",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    },
    {
        "name": "Aggarwal Real Estate & Builders",
        "phone": "+91 98731 22334",
        "website": "https://aggarwalestates.example.in",
        "address": "Plot 42, Pocket 16, Sector 24, Rohini, Delhi 110085",
        "rating": 4.9,
        "reviews_count": 112,
        "industry": "Property Consultant",
        "contacts": [
            {
                "first_name": "Vikram",
                "last_name": "Aggarwal",
                "title": "Managing Director",
                "email": "vikram@aggarwalestates.example.in",
                "phone": "+91 98731 22334",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    },
    {
        "name": "Gupta & Sons Property Advisors",
        "phone": "+91 99100 44556",
        "website": "https://guptaproperties.example.in",
        "address": "CSC Pocket 2, Sector 7, Rohini, Delhi 110085",
        "rating": 4.7,
        "reviews_count": 96,
        "industry": "Real Estate Agency",
        "contacts": [
            {
                "first_name": "Manoj",
                "last_name": "Gupta",
                "title": "Senior Advisor",
                "email": "manoj@guptaproperties.example.in",
                "phone": "+91 99100 44556",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    },
    {
        "name": "Shree Sai Estates Rohini",
        "phone": "+91 98188 77665",
        "website": "https://shreesaiestates.example.in",
        "address": "Pocket 3, Sector 22, Rohini, Delhi 110086",
        "rating": 4.6,
        "reviews_count": 48,
        "industry": "Real Estate Consultant",
        "contacts": [
            {
                "first_name": "Sunil",
                "last_name": "Kumar",
                "title": "Owner",
                "email": "sunil@shreesaiestates.example.in",
                "phone": "+91 98188 77665",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    },
    {
        "name": "Metro Prime Realty Associates",
        "phone": "+91 98101 99887",
        "website": "https://metroprimerealty.example.in",
        "address": "Main Road, Sector 25, Rohini, Delhi 110085",
        "rating": 4.8,
        "reviews_count": 63,
        "industry": "Real Estate Agency",
        "contacts": [
            {
                "first_name": "Amit",
                "last_name": "Verma",
                "title": "Partner",
                "email": "amit@metroprimerealty.example.in",
                "phone": "+91 98101 99887",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    },
    {
        "name": "Capital Land & Building Consultants",
        "phone": "+91 98711 55443",
        "website": "https://capitallanddelhi.example.in",
        "address": "Sector 34, Rohini Near UER-II, Delhi 110039",
        "rating": 4.5,
        "reviews_count": 31,
        "industry": "Land Consultant",
        "contacts": [
            {
                "first_name": "Praveen",
                "last_name": "Joshi",
                "title": "Principal Consultant",
                "email": "praveen@capitallanddelhi.example.in",
                "phone": "+91 98711 55443",
                "is_verified": True,
                "verification_status": "valid"
            }
        ]
    }
]

async def seed_initial_data_if_empty():
    """Populates database with sample Rohini leads, initial scrape job, and sample campaign."""
    async with async_session_maker() as db:
        stmt = select(Business)
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return  # Database already seeded

        logger.info("Seeding initial LeadForge data...")

        # 1. Insert Businesses & Contacts
        for item in SAMPLE_BUSINESSES:
            b = Business(
                name=item["name"],
                phone=item["phone"],
                website=item["website"],
                address=item["address"],
                rating=item["rating"],
                reviews_count=item["reviews_count"],
                industry=item["industry"],
                extra_data={"query": "Real Estate Agents in Rohini Delhi", "seeded": True}
            )
            db.add(b)
            await db.flush()

            for c in item["contacts"]:
                phone_digits = "".join(filter(str.isdigit, c["phone"]))
                contact = Contact(
                    business_id=b.id,
                    first_name=c["first_name"],
                    last_name=c["last_name"],
                    title=c["title"],
                    email=c["email"],
                    phone=c["phone"],
                    whatsapp_link=f"https://wa.me/{phone_digits}",
                    is_verified=c["is_verified"],
                    verification_status=c["verification_status"],
                    source="google_maps_seed"
                )
                db.add(contact)

        # 2. Insert Scrape Job Record
        job = ScrapeJob(
            query="Real Estate Agents & Property Dealers Rohini Delhi",
            status="completed",
            total_found=len(SAMPLE_BUSINESSES),
            leads_saved=len(SAMPLE_BUSINESSES),
            finished_at=datetime.utcnow()
        )
        db.add(job)

        # 3. Insert Default Mailbox Placeholder
        mb = Mailbox(
            email="outreach@plotbook.webforge.me",
            password="change-in-settings",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            first_name="PlotBook",
            last_name="Outreach",
            daily_limit=50,
            sent_today=0,
            is_active=True
        )
        db.add(mb)
        await db.flush()

        # 4. Insert Sample Outreach Campaign
        camp = Campaign(
            name="Rohini Real Estate Dealers — DDA Blueprint Intro",
            status=CampaignStatus.ACTIVE.value
        )
        db.add(camp)
        await db.flush()

        step = CampaignStep(
            campaign_id=camp.id,
            step_number=1,
            subject="Quick question regarding your {{business_name}} property due diligence",
            body_text="Hi {{first_name}},\n\nI noticed the great work {{business_name}} is doing with property transactions in {{city}}.\n\nQuick question: how do you currently verify original DDA plot layout plans, pocket maps, and circle rates for clients before drafting sale agreements?\n\nWe recently digitized all 362+ official DDA layout plans across all 36 Rohini sectors on PlotBook (https://plotbook.webforge.me) at native pixel zoom with instant circle rate calculations.\n\nWould you be open to a 2-minute look to see how it can save your team hours on client due diligence?\n\nBest regards,\nPlotBook Team",
            body_html="<p>Hi {{first_name}},</p><p>I noticed the great work <strong>{{business_name}}</strong> is doing with property transactions in {{city}}.</p><p>Quick question: how do you currently verify original DDA plot layout plans, pocket maps, and circle rates for clients before drafting sale agreements?</p><p>We recently digitized all 362+ official DDA layout plans across all 36 Rohini sectors on <a href='https://plotbook.webforge.me'>PlotBook</a> at native pixel zoom with instant circle rate calculations.</p><p>Would you be open to a 2-minute look to see how it can save your team hours on client due diligence?</p><p>Best regards,<br/><strong>PlotBook Team</strong></p>",
            delay_days=0
        )
        db.add(step)

        await db.commit()
        logger.info("Database seeding completed successfully.")
