"""
Seed script - Creates demo data for development.

Run with: python -m scripts.seed_demo
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.tenant import Tenant
from app.models.user import User
from app.models.cost_nature import CostNature
from app.models.supplier import Supplier
from app.models.contract import Contract, ContractRate
from app.models.rate_catalog import RateCatalog
from app.models.trip import Trip, TripDay, TripPaxConfig
from app.models.formula import Formula
from app.models.item import Item


async def create_tenant(db: AsyncSession) -> Tenant:
    """Create demo tenant."""
    tenant = Tenant(
        name="Nomadays Demo",
        slug="nomadays-demo",
        settings_json={
            "default_currency": "EUR",
            "default_margin_pct": 30,
            "margin_type": "margin",
            "vat_pct": 0,
            "ai_price_check_threshold": 15,
            "contract_alert_days": 30,
        },
    )
    db.add(tenant)
    await db.flush()
    print(f"✅ Created tenant: {tenant.name} (ID: {tenant.id})")
    return tenant


async def create_users(db: AsyncSession, tenant: Tenant) -> list[User]:
    """Create demo users."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    users = []
    user_data = [
        ("Admin User", "admin@nomadays-demo.com", "admin", "admin123"),
        ("Manager User", "manager@nomadays-demo.com", "manager", "manager123"),
        ("Sales User", "sales@nomadays-demo.com", "sales", "sales123"),
    ]

    for name, email, role, password in user_data:
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=pwd_context.hash(password),
            name=name,
            role=role,
            is_active=True,
        )
        db.add(user)
        users.append(user)

    await db.flush()
    print(f"✅ Created {len(users)} users")
    return users


async def create_cost_natures(db: AsyncSession, tenant: Tenant) -> dict:
    """Create cost nature types."""
    natures = {}
    nature_data = [
        ("Hébergement", True, False, False),
        ("Transport", True, False, False),
        ("Activité", True, False, False),
        ("Guide", False, True, False),
        ("Restaurant", True, False, False),
        ("Entrées/Visites", True, False, False),
        ("Assurance", False, False, False),
        ("Frais agence", False, False, True),
    ]

    for name, triggers_booking, triggers_payroll, triggers_advance in nature_data:
        nature = CostNature(
            tenant_id=tenant.id,
            name=name,
            triggers_booking=triggers_booking,
            triggers_payroll=triggers_payroll,
            triggers_advance=triggers_advance,
        )
        db.add(nature)
        natures[name] = nature

    await db.flush()
    print(f"✅ Created {len(natures)} cost natures")
    return natures


async def create_suppliers(db: AsyncSession, tenant: Tenant) -> dict:
    """Create demo suppliers."""
    suppliers = {}
    supplier_data = [
        ("Hotel Marrakech Riad", "hotel", "MAD", "Marrakech"),
        ("Atlas Transport", "transport", "MAD", "Marrakech"),
        ("Desert Tours Morocco", "activity", "EUR", "Merzouga"),
        ("Fès Médina Guide", "guide", "MAD", "Fès"),
        ("Restaurant Dar Yacout", "restaurant", "MAD", "Marrakech"),
        ("Kasbah Tamadot", "hotel", "EUR", "Atlas Mountains"),
    ]

    for name, supplier_type, currency, location in supplier_data:
        supplier = Supplier(
            tenant_id=tenant.id,
            name=name,
            type=supplier_type,
            default_currency=currency,
            country="Maroc",
            city=location,
            is_active=True,
        )
        db.add(supplier)
        suppliers[name] = supplier

    await db.flush()
    print(f"✅ Created {len(suppliers)} suppliers")
    return suppliers


async def create_contracts(
    db: AsyncSession,
    tenant: Tenant,
    suppliers: dict,
) -> dict:
    """Create contracts with rates."""
    contracts = {}

    # Hotel Marrakech Riad contract
    hotel_contract = Contract(
        tenant_id=tenant.id,
        supplier_id=suppliers["Hotel Marrakech Riad"].id,
        name="Contrat 2024 - Riad Marrakech",
        valid_from=date(2024, 1, 1),
        valid_to=date(2024, 12, 31),
        currency="MAD",
        commission_pct=Decimal("10"),
        notes="Tarifs négociés pour la saison 2024",
    )
    db.add(hotel_contract)
    await db.flush()

    # Add rates for the hotel
    hotel_rates = [
        ("Chambre Standard", Decimal("800"), "single"),
        ("Chambre Standard", Decimal("1200"), "double"),
        ("Suite Junior", Decimal("1500"), "double"),
        ("Suite Deluxe", Decimal("2500"), "double"),
    ]

    for name, cost, room_type in hotel_rates:
        rate = ContractRate(
            tenant_id=tenant.id,
            contract_id=hotel_contract.id,
            name=f"{name} ({room_type})",
            unit_type="night",
            unit_cost=cost,
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 12, 31),
            meta_json={"room_type": room_type},
        )
        db.add(rate)

    contracts["Hotel Marrakech Riad"] = hotel_contract

    # Transport contract
    transport_contract = Contract(
        tenant_id=tenant.id,
        supplier_id=suppliers["Atlas Transport"].id,
        name="Contrat Transport 2024",
        valid_from=date(2024, 1, 1),
        valid_to=date(2024, 12, 31),
        currency="MAD",
    )
    db.add(transport_contract)
    await db.flush()

    transport_rates = [
        ("Minivan 7 places", Decimal("1500"), "day"),
        ("4x4 Land Cruiser", Decimal("2200"), "day"),
        ("Bus 20 places", Decimal("3500"), "day"),
        ("Transfert Aéroport", Decimal("400"), "trip"),
    ]

    for name, cost, unit_type in transport_rates:
        rate = ContractRate(
            tenant_id=tenant.id,
            contract_id=transport_contract.id,
            name=name,
            unit_type=unit_type,
            unit_cost=cost,
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 12, 31),
        )
        db.add(rate)

    contracts["Atlas Transport"] = transport_contract

    await db.flush()
    print(f"✅ Created {len(contracts)} contracts with rates")
    return contracts


async def create_trip_template(
    db: AsyncSession,
    tenant: Tenant,
    user: User,
    cost_natures: dict,
    suppliers: dict,
) -> Trip:
    """Create a complete trip template."""
    # Create trip
    trip = Trip(
        tenant_id=tenant.id,
        created_by_id=user.id,
        name="Découverte du Maroc - 7 jours",
        type="template",
        duration_days=7,
        destination_country="Maroc",
        default_currency="EUR",
        margin_pct=Decimal("30"),
        margin_type="margin",
        status="active",
    )
    db.add(trip)
    await db.flush()

    # Create pax configurations
    pax_configs = [
        ("2 adultes", 2, {"adult": 2}),
        ("4 adultes", 4, {"adult": 4}),
        ("2 adultes + 2 enfants", 4, {"adult": 2, "child": 2}),
        ("6 adultes", 6, {"adult": 6}),
    ]

    for label, total_pax, args in pax_configs:
        config = TripPaxConfig(
            tenant_id=tenant.id,
            trip_id=trip.id,
            label=label,
            total_pax=total_pax,
            args_json=args,
        )
        db.add(config)

    # Create days
    days_data = [
        (1, "Arrivée à Marrakech", "Aéroport", "Marrakech", "Accueil et transfert vers le riad"),
        (2, "Visite de Marrakech", "Marrakech", "Marrakech", "Journée découverte de la médina"),
        (3, "Route vers le désert", "Marrakech", "Ouarzazate", "Traversée du Haut Atlas"),
        (4, "Désert de Merzouga", "Ouarzazate", "Merzouga", "Nuit dans le désert"),
        (5, "Gorges du Dadès", "Merzouga", "Dadès", "Route des kasbahs"),
        (6, "Retour Marrakech", "Dadès", "Marrakech", "Retour via les routes panoramiques"),
        (7, "Départ", "Marrakech", "Aéroport", "Transfert aéroport et départ"),
    ]

    for day_num, title, loc_from, loc_to, desc in days_data:
        day = TripDay(
            tenant_id=tenant.id,
            trip_id=trip.id,
            day_number=day_num,
            title=title,
            description=desc,
            location_from=loc_from,
            location_to=loc_to,
            sort_order=day_num,
        )
        db.add(day)
        await db.flush()

        # Add formulas and items for key days
        if day_num == 1:
            # Day 1: Arrival
            formula = Formula(
                tenant_id=tenant.id,
                trip_day_id=day.id,
                name="Transfert arrivée",
                service_day_start=1,
                service_day_end=1,
                sort_order=1,
            )
            db.add(formula)
            await db.flush()

            item = Item(
                tenant_id=tenant.id,
                formula_id=formula.id,
                name="Transfert aéroport - Riad",
                cost_nature_id=cost_natures["Transport"].id,
                supplier_id=suppliers["Atlas Transport"].id,
                currency="MAD",
                unit_cost=Decimal("400"),
                pricing_method="quotation",
                ratio_categories="all",
                ratio_per=1,
                ratio_type="set",
                times_type="fixed",
                times_value=1,
                sort_order=1,
            )
            db.add(item)

            # Accommodation formula
            formula2 = Formula(
                tenant_id=tenant.id,
                trip_day_id=day.id,
                name="Hébergement Marrakech",
                service_day_start=1,
                service_day_end=2,
                sort_order=2,
            )
            db.add(formula2)
            await db.flush()

            item2 = Item(
                tenant_id=tenant.id,
                formula_id=formula2.id,
                name="Chambre double Riad",
                cost_nature_id=cost_natures["Hébergement"].id,
                supplier_id=suppliers["Hotel Marrakech Riad"].id,
                currency="MAD",
                unit_cost=Decimal("1200"),
                pricing_method="quotation",
                ratio_categories="adult,teen",
                ratio_per=2,
                ratio_type="ratio",
                times_type="service_days",
                times_value=1,
                sort_order=1,
            )
            db.add(item2)

        elif day_num == 2:
            # Day 2: Marrakech visit
            formula = Formula(
                tenant_id=tenant.id,
                trip_day_id=day.id,
                name="Visite guidée Médina",
                service_day_start=2,
                service_day_end=2,
                sort_order=1,
            )
            db.add(formula)
            await db.flush()

            item = Item(
                tenant_id=tenant.id,
                formula_id=formula.id,
                name="Guide francophone",
                cost_nature_id=cost_natures["Guide"].id,
                currency="MAD",
                unit_cost=Decimal("800"),
                pricing_method="quotation",
                ratio_categories="all",
                ratio_per=10,
                ratio_type="ratio",
                times_type="fixed",
                times_value=1,
                sort_order=1,
            )
            db.add(item)

            item2 = Item(
                tenant_id=tenant.id,
                formula_id=formula.id,
                name="Entrées monuments",
                cost_nature_id=cost_natures["Entrées/Visites"].id,
                currency="MAD",
                unit_cost=Decimal("120"),
                pricing_method="quotation",
                ratio_categories="adult,teen",
                ratio_per=1,
                ratio_type="ratio",
                times_type="fixed",
                times_value=1,
                sort_order=2,
            )
            db.add(item2)

        elif day_num == 3:
            # Day 3: Desert road
            formula = Formula(
                tenant_id=tenant.id,
                trip_day_id=day.id,
                name="Transport journée",
                service_day_start=3,
                service_day_end=3,
                sort_order=1,
            )
            db.add(formula)
            await db.flush()

            item = Item(
                tenant_id=tenant.id,
                formula_id=formula.id,
                name="4x4 avec chauffeur",
                cost_nature_id=cost_natures["Transport"].id,
                supplier_id=suppliers["Atlas Transport"].id,
                currency="MAD",
                unit_cost=Decimal("2200"),
                pricing_method="quotation",
                ratio_categories="all",
                ratio_per=4,
                ratio_type="ratio",
                times_type="fixed",
                times_value=1,
                sort_order=1,
            )
            db.add(item)

        elif day_num == 4:
            # Day 4: Desert
            formula = Formula(
                tenant_id=tenant.id,
                trip_day_id=day.id,
                name="Excursion désert",
                service_day_start=4,
                service_day_end=4,
                sort_order=1,
            )
            db.add(formula)
            await db.flush()

            item = Item(
                tenant_id=tenant.id,
                formula_id=formula.id,
                name="Nuit bivouac + dromadaires",
                cost_nature_id=cost_natures["Activité"].id,
                supplier_id=suppliers["Desert Tours Morocco"].id,
                currency="EUR",
                unit_cost=Decimal("85"),
                pricing_method="quotation",
                ratio_categories="adult,teen,child",
                ratio_per=1,
                ratio_type="ratio",
                times_type="fixed",
                times_value=1,
                sort_order=1,
            )
            db.add(item)

    await db.flush()
    print(f"✅ Created trip template: {trip.name} (ID: {trip.id})")
    return trip


async def seed_demo_data():
    """Main seed function."""
    print("🌱 Starting demo data seed...")

    async with async_session_maker() as db:
        # Check if data already exists
        result = await db.execute(select(Tenant).limit(1))
        if result.scalar_one_or_none():
            print("⚠️  Data already exists. Skipping seed.")
            return

        # Create all demo data
        tenant = await create_tenant(db)
        users = await create_users(db, tenant)
        cost_natures = await create_cost_natures(db, tenant)
        suppliers = await create_suppliers(db, tenant)
        contracts = await create_contracts(db, tenant, suppliers)
        trip = await create_trip_template(db, tenant, users[0], cost_natures, suppliers)

        await db.commit()
        print("✅ Demo data seed completed!")
        print(f"\n📝 Login credentials:")
        print(f"   Admin: admin@nomadays-demo.com / admin123")
        print(f"   Manager: manager@nomadays-demo.com / manager123")
        print(f"   Sales: sales@nomadays-demo.com / sales123")


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
