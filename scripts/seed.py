"""Idempotent seed script.

Connects to the docker MySQL, creates the products table if needed, and inserts
realistic pizzas and drinks so the example queries match. Safe to re-run: rows
are upserted by name.
"""
import os
import sys

# Allow `python scripts/seed.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.db import Product, get_sessionmaker, init_db  # noqa: E402

PRODUCTS = [
    # name, description, price, category
    ("Pepperoni Cheese Pizza", "Classic pizza with pepperoni and mozzarella cheese", 12.99, "pizza"),
    ("Cheese Pizza", "Mozzarella cheese pizza on tomato base", 9.99, "pizza"),
    ("Margherita Pizza", "Tomato, fresh mozzarella and basil", 10.99, "pizza"),
    ("Veggie Supreme Pizza", "Peppers, onions, mushrooms, olives and sweetcorn", 13.49, "pizza"),
    ("Hawaiian Pizza", "Ham and pineapple with mozzarella", 12.49, "pizza"),
    ("BBQ Chicken Pizza", "Grilled chicken, red onion and BBQ sauce", 13.99, "pizza"),
    ("Meat Feast Pizza", "Pepperoni, ham, beef and sausage", 14.49, "pizza"),
    ("Coca-Cola 330ml", "Classic Coca-Cola can", 1.99, "drink"),
    ("Coke Zero 330ml", "Zero sugar Coca-Cola can", 1.99, "drink"),
    ("Sprite 330ml", "Lemon-lime sparkling drink", 1.99, "drink"),
    ("Fanta Orange 330ml", "Orange flavoured sparkling drink", 1.99, "drink"),
    ("Bottled Water", "500ml still mineral water", 1.49, "drink"),
    ("Sparkling Water 500ml", "Carbonated mineral water", 1.69, "drink"),
    ("Orange Juice 330ml", "Freshly squeezed orange juice", 2.49, "drink"),
]


def seed() -> None:
    init_db()
    Session = get_sessionmaker()
    inserted = updated = 0
    with Session() as session:
        for name, description, price, category in PRODUCTS:
            existing = (
                session.query(Product).filter(Product.name == name).one_or_none()
            )
            if existing is None:
                session.add(
                    Product(
                        name=name,
                        description=description,
                        price=price,
                        category=category,
                        is_available=True,
                    )
                )
                inserted += 1
            else:
                existing.description = description
                existing.price = price
                existing.category = category
                existing.is_available = True
                updated += 1
        session.commit()
    print(f"Seed complete: {inserted} inserted, {updated} updated, {len(PRODUCTS)} total.")


if __name__ == "__main__":
    seed()
