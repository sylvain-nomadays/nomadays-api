# Nomadays API

Backend API for the Nomadays SaaS platform - A comprehensive solution for DMC (Destination Management Companies).

## Features

- **Quotation Engine**: Calculate trip costs with complex pricing rules
- **Contract Management**: Track supplier contracts and rates
- **AI Price Controller**: Detect pricing anomalies and expiring contracts
- **Multi-tenant Architecture**: Complete data isolation between DMCs

## Tech Stack

- **FastAPI** (Python 3.12+)
- **SQLAlchemy 2.0** with async support
- **PostgreSQL** (via Supabase)
- **Alembic** for migrations
- **JWT** authentication

## Quick Start

### 1. Install dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Seed demo data

```bash
python -m scripts.seed_demo
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

API will be available at http://localhost:8000

## Docker

```bash
docker-compose up --build
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
nomadays-api/
├── alembic/              # Database migrations
├── app/
│   ├── api/              # API routes
│   │   ├── auth.py       # Authentication
│   │   ├── trips.py      # Trip management
│   │   ├── quotation.py  # Quotation engine
│   │   ├── suppliers.py  # Supplier management
│   │   ├── contracts.py  # Contract management
│   │   ├── alerts.py     # AI alerts
│   │   └── dashboard.py  # Dashboard stats
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   │   └── quotation_engine.py  # Core pricing logic
│   ├── config.py         # Settings
│   ├── database.py       # DB connection
│   └── main.py           # FastAPI app
├── scripts/
│   └── seed_demo.py      # Demo data
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```

## Core Concepts

### Quotation Engine

The quotation engine calculates trip costs using:

- **Ratio rules**: Calculate quantities based on pax categories (adult/teen/child/baby)
- **Temporal multipliers**: Apply costs per service day, total trip, or fixed
- **Seasonal pricing**: Adjust costs based on travel dates
- **Multiple margin types**: margin, markup, fixed amount

### Multi-tenancy

All data is isolated by `tenant_id`. Each DMC sees only their own:
- Suppliers
- Contracts
- Trips
- Users

## Demo Credentials

After running seed script:

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@nomadays-demo.com | admin123 |
| Manager | manager@nomadays-demo.com | manager123 |
| Sales | sales@nomadays-demo.com | sales123 |
