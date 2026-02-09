from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from uuid import uuid4

from services.api.app.db.database import db_session
from services.api.app.db.init_db import init_db
from services.api.app.db.models import (
    BookingVendor,
    Household,
    Preference,
    Subscription,
    User,
    UsualItem,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed minimal Halo MVP data")
    parser.add_argument("--household-id", default="hh-1")
    parser.add_argument("--household-name", default="Halo Household")
    parser.add_argument("--user-1", default="u-1")
    parser.add_argument("--user-1-name", default="User 1")
    parser.add_argument("--user-2", default="u-2")
    parser.add_argument("--user-2-name", default="User 2")
    args = parser.parse_args()

    init_db()

    db = db_session()
    try:
        if db.get(Household, args.household_id) is None:
            db.add(Household(id=args.household_id, name=args.household_name))

        for uid, name in ((args.user_1, args.user_1_name), (args.user_2, args.user_2_name)):
            if db.get(User, uid) is None:
                db.add(User(id=uid, household_id=args.household_id, display_name=name))

        if db.get(Preference, args.household_id) is None:
            db.add(
                Preference(
                    household_id=args.household_id,
                    default_merchant="amazon",
                    default_booking_vendor=None,
                )
            )

        # Usual items
        existing_usual = (
            db.query(UsualItem).filter(UsualItem.household_id == args.household_id).limit(1).count()
        )
        if existing_usual == 0:
            for name, qty in (
                ("paper towels", 1),
                ("detergent", 1),
            ):
                db.add(
                    UsualItem(
                        id=uuid4().hex,
                        household_id=args.household_id,
                        name=name,
                        quantity=qty,
                    )
                )

        # Subscriptions
        existing_subs = (
            db.query(Subscription)
            .filter(Subscription.household_id == args.household_id)
            .limit(1)
            .count()
        )
        if existing_subs == 0:
            now = datetime.utcnow()
            for name, cost, renewal in (
                ("Netflix", 1599, now + timedelta(days=15)),
                ("Spotify", 1099, now + timedelta(days=7)),
            ):
                db.add(
                    Subscription(
                        id=uuid4().hex,
                        household_id=args.household_id,
                        name=name,
                        monthly_cost_cents=cost,
                        renewal_date=renewal,
                    )
                )

        # Booking vendor
        existing_vendor = (
            db.query(BookingVendor)
            .filter(BookingVendor.household_id == args.household_id)
            .limit(1)
            .count()
        )
        if existing_vendor == 0:
            db.add(
                BookingVendor(
                    id=uuid4().hex,
                    household_id=args.household_id,
                    name="Mock Cleaner Co",
                    default_service_type="cleaning",
                    price_estimate_cents=12000,
                )
            )

        db.commit()
        print(f"Seeded household={args.household_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
