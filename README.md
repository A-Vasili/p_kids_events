# P Kids Events

A full-stack Django web application for discovering, building, booking, and managing children’s party events.

- **Live website:** [https://p-kids-events.onrender.com/](https://p-kids-events.onrender.com/)
- **Source repository:** [https://github.com/A-Vasili/p_kids_events](https://github.com/A-Vasili/p_kids_events)
- **Course:** ITC4214 — Internet Programming
- **Student:** Athanasios Vasilis
- **Student ID:** 277690

> This is an academic demonstration project. Checkout is simulated: no real payment is taken and full card details are never stored.

---

## Project overview

P Kids Events represents an imaginary children’s event company. The application supports the complete journey from discovering a party idea to creating a booking, assigning a worker, completing the event, and collecting verified customer feedback.

The project goes beyond a static company website. It includes:

- a searchable catalogue with categories and subcategories;
- eight capacity-based party packages and twenty optional experiences;
- a multi-step party builder and simulated shopping cart;
- customer registration, profiles, dashboards, and booking history;
- recommendations based on catalogue and booking information;
- verified ratings, private feedback, and optional public testimonials;
- worker availability, schedules, assignment offers, and completion actions;
- a secure customer-support chat;
- a custom management panel for Owners and Administrators;
- delegated Pricing Manager and Chat Responder permissions;
- analytics and audit history;
- English and Greek customer-facing interface text;
- responsive light and dark themes;
- production deployment with PostgreSQL on Render.

---

## Assessment requirements covered

| Requirement | Implementation |
|---|---|
| Dynamic catalogue | Packages and experiences stored in Django models and browsed by category/subcategory |
| Normal search | Search by name and descriptive text |
| Advanced filtering | Price, capacity, duration, rating, featured status, category, and item type |
| Registration and authentication | Sign-up, sign-in, sign-out, secure sessions, and password validation |
| User profile | Customer profile view and update form |
| Personalised dashboard | Bookings, statuses, selected items, totals, review access, and recent activity |
| Administrative panel | Custom management panel for catalogue, categories, users, bookings, workers, chat, and analytics |
| Role-based security | Customer, Worker, Pricing Manager, Chat Responder, Owner, and Administrator boundaries |
| Recommender system | Suggested packages and add-ons based on catalogue and completed-booking information |
| Ratings and reviews | AJAX star ratings, private comments, and optional testimonials |
| Shopping cart | Session-based party builder with server-calculated totals and simulated checkout |
| Database integration | Related Django models backed by PostgreSQL in production |
| Secure deployment | Render, Gunicorn, WhiteNoise, HTTPS, environment variables, and production checks |

---

## Main features

### Public visitors

- Browse packages and optional experiences.
- Navigate categories and subcategories.
- Search and apply advanced filters.
- View package and experience detail pages.
- See ratings, approved testimonials, and recommendations.
- Use English or Greek interface text.
- Use light or dark mode.
- Open the support-chat launcher and receive sign-in options.

### Customers

- Register, sign in, sign out, and update profile information.
- Choose one of eight fixed-price packages, each with a defined capacity.
- Add optional experiences from a catalogue of twenty choices.
- View live party totals and recommendations.
- Complete a multi-step simulated checkout.
- View current and historical bookings in a private dashboard.
- Continue one private support conversation with the P Kids Events team.
- Receive unread chat indicators.
- Rate a completed package and its booked experiences.
- Keep written feedback private or consent to publication as a testimonial.
- Withdraw testimonial publication consent later.

### Workers

- Access a dedicated operations portal.
- View assignment offers intended for the signed-in worker.
- Accept or decline offers.
- Record available, preferred, and unavailable periods.
- View a personal schedule and workload.
- Open the operational details required for assigned events.
- Mark an eligible party as completed after it has taken place.
- Receive delegated pricing or chat privileges when authorised.

### Owners and Administrators

- Use a custom management panel instead of Django Admin.
- Manage packages, experiences, categories, images, prices, capacities, and durations.
- View and update bookings.
- Assign or reassign workers.
- Review cases where automatic assignment cannot find a suitable worker.
- Manage customer and worker accounts.
- Grant or revoke Pricing Manager and Chat Responder access.
- View worker schedules, availability, conflicts, and workload.
- Read and reply to customer-support chats.
- View booking, catalogue, rating, testimonial, and worker analytics.
- Review audit records for important management actions.
- Mark eligible parties as completed and unlock customer review access.

---

## Technology stack

| Technology | Purpose |
|---|---|
| Python 3.12+ | Main programming language |
| Django 5.2 | Backend framework, authentication, forms, ORM, sessions, templates, and security |
| PostgreSQL | Production relational database |
| SQLite | Lightweight local-development and test database |
| HTML5 | Semantic page structure and accessible forms |
| CSS3 | Responsive layouts, component styling, light mode, and dark mode |
| Bootstrap | Responsive layout support and reusable interface patterns |
| Django Template Language | Server-rendered dynamic HTML |
| Vanilla JavaScript | Interactive controls without a frontend framework |
| Fetch API / AJAX | Ratings, recommendations, live builder updates, and chat requests |
| Pillow | Catalogue-image validation and processing |
| Gunicorn | Production WSGI application server |
| WhiteNoise | Production delivery of collected static assets |
| Render | Web hosting, managed PostgreSQL, HTTPS, and persistent media storage |
| Git and GitHub | Version control, source hosting, and deployment integration |

Python package versions are recorded in `requirements.txt`.

---

## Architecture

The project follows Django’s Model–View–Template structure and adds a service layer for important business actions.

```text
Browser
   |
   v
URL configuration
   |
   v
Views and forms
   |
   v
Business services
   |
   v
Django ORM and PostgreSQL
   |
   +--> Templates return HTML
   +--> JavaScript enhances interactions
   +--> CSS and Bootstrap control presentation
```

### Django applications

| Application | Responsibility |
|---|---|
| `accounts` | Registration, authentication, profiles, role groups, and permission helpers |
| `party_builder` | Catalogue, party builder, checkout, recommendations, reviews, and testimonials |
| `operations` | Worker portal, assignments, schedules, management panel, analytics, and audit history |
| `communications` | Customer-support chat, staff replies, and personal unread state |
| `core` | Public pages, testimonials, redirects, and shared security middleware |
| `config` | Project settings, root URLs, WSGI, and ASGI configuration |

### Why a service layer is used

Views mainly handle requests, forms, messages, and responses. Sensitive business actions are kept in service modules, including:

- creating bookings;
- calculating trusted totals;
- assigning workers;
- changing booking status;
- completing parties;
- saving reviews;
- changing staff permissions;
- sending chat messages;
- removing or archiving catalogue records.

This keeps the same permission, validation, transaction, and audit rules consistent across different pages.

---

## Role and permission model

| Role | Customer area | Worker portal | Catalogue pricing | Customer messages | Full management |
|---|---:|---:|---:|---:|---:|
| Public visitor | Browse only | No | No | Sign-in prompt | No |
| Customer | Yes | No | No | Own chat | No |
| Worker | Limited | Yes | No | No | No |
| Pricing Manager | Limited | Yes | Yes | No | Limited |
| Chat Responder | Limited | Yes | No | Yes | Limited |
| Owner | Yes | Yes | Yes | Yes | Yes |
| Administrator | Yes | Yes | Yes | Yes | Yes |

Navigation links reflect the current role, but links are not treated as security. Protected views, querysets, forms, and services check permissions again on the server.

Django Admin remains intentionally unavailable. Business management is performed through the project’s custom management interface.

---

## Important workflows

### Party booking

```text
Browse Party Ideas
        |
        v
Choose a capacity-based package
        |
        v
Select optional experiences
        |
        v
Enter contact and event details
        |
        v
Review server-calculated total
        |
        v
Complete simulated checkout
        |
        v
Store booking and price snapshots
        |
        v
Begin worker assignment
```

The browser submits record identifiers, not trusted prices. Django reloads active catalogue records and recalculates the total using database values.

Completed bookings store package and add-on price snapshots. Later catalogue changes therefore do not alter historical booking totals.

### Automatic worker assignment

```text
New booking
   |
   v
Find active workers
   |
   v
Check availability and unavailable periods
   |
   v
Exclude time conflicts
   |
   v
Check daily workload limits
   |
   v
Rank suitable workers
   |
   v
Create an assignment offer
```

When no worker is suitable, the booking remains available for management review and manual assignment.

### Party completion and reviews

```text
Eligible party takes place
        |
        v
Owner, Administrator, or accepted assigned worker marks it done
        |
        v
Booking becomes Completed
        |
        v
Customer dashboard displays review access
        |
        v
Customer verifies the private review code
        |
        v
Customer rates only the package and experiences actually booked
```

Written feedback remains private unless the customer separately consents to testimonial publication.

### Customer chat

- Each customer has one continuing support conversation.
- Anonymous visitors cannot send messages.
- Customers see staff replies as coming from the **P Kids Events Team**.
- Owners, Administrators, and explicitly delegated Chat Responders can reply.
- Unread state is tracked separately for every user.
- JavaScript provides the floating panel and periodic refresh.
- A normal full-page Django form remains available when JavaScript is disabled.

---

## Advanced implementation details

### Server-trusted pricing

Package and add-on prices are always loaded from the database. The server does not trust a total submitted by JavaScript or hidden form fields.

### Database transactions

Multi-step changes use `transaction.atomic()` so related updates either all succeed or all roll back. Examples include assignment acceptance, booking completion, review saving, and chat replies.

### Row locking

Sensitive updates use `select_for_update()` on PostgreSQL to prevent simultaneous requests from changing the same booking, assignment, review, or conversation inconsistently.

### Historical snapshots

The application stores important historical values, including:

- package price at checkout;
- add-on unit prices;
- total price;
- package-capacity label;
- sender name and role for chat history.

This keeps old business records understandable even when current catalogue or account details later change.

### Archive and deletion protection

Records that form part of booking, review, audit, assignment, or chat history are protected from unsafe deletion. Referenced catalogue records are normally archived rather than removed.

### Recommendations

Recommendation logic combines catalogue relationships, featured items, ratings, and completed-booking patterns. Fallback suggestions remain available when there is not yet enough historical data.

---

## Database overview

The project contains multiple related models, including:

```text
Django User
|-- CustomerProfile
|-- WorkerProfile
|-- PartyBuild bookings
|-- CustomerChat

Category
|-- Child categories
|-- PartyPackage
|-- AddonExperience

PartyBuild
|-- PartyPackage
|-- PartyBuildAddon
|-- PartyAssignment
|-- PartyReview

PartyReview
|-- AddonRating

CustomerChat
|-- ChatMessage
|-- ChatReadState
```

Key models include:

- `CustomerProfile`
- `WorkerProfile`
- `Category`
- `PartyPackage`
- `AddonExperience`
- `PartyBuild`
- `PartyBuildAddon`
- `PartyAssignment`
- `WorkerAvailability`
- `PartyReview`
- `AddonRating`
- `CustomerChat`
- `ChatMessage`
- `ChatReadState`
- `AuditEvent`

---

## Security

The project uses Django’s built-in protections together with additional application rules:

- password hashing and validation;
- login-required and role-based views;
- CSRF protection for forms and AJAX requests;
- automatic escaping of user-supplied template content;
- Django ORM queries rather than manually assembled SQL;
- server-side form and service validation;
- restricted object querysets to prevent cross-account access;
- secure session and CSRF cookies in production;
- HTTPS redirection and proxy-aware security settings;
- Content Security Policy and related response headers;
- UUIDs for public booking and chat URLs;
- image extension, content, size, and filename validation;
- database transactions and row locks;
- audit records for sensitive management actions;
- exclusion of passwords, card security codes, review codes, and message bodies from audit metadata.

The simulated checkout does not charge money and does not store a complete card number or CVV.

---

## Accessibility and responsive design

The interface includes:

- semantic headings and landmarks;
- a skip-to-content link;
- visible labels and validation errors;
- keyboard-operable custom controls;
- visible focus states;
- screen-reader status messages;
- alternative text for catalogue images;
- controls that do not rely on colour alone;
- reduced-motion support where animation is used;
- mobile, tablet, and desktop layouts;
- light and dark themes;
- English and Greek customer-interface text;
- no-JavaScript fallbacks for essential forms and chat.

---

## Project structure

```text
p_kids_events/
|-- accounts/
|-- communications/
|-- config/
|-- core/
|-- operations/
|   |-- services/
|   `-- templatetags/
|-- party_builder/
|-- static/
|   |-- assets/
|   |-- css/
|   `-- js/
|-- templates/
|-- build.sh
|-- manage.py
|-- render.yaml
|-- requirements.txt
|-- .env.example
|-- .python-version
`-- README.md
```

Local-only or generated files such as `.venv/`, `db.sqlite3`, `.env`, `staticfiles/`, cache folders, and compiled Python files are excluded from version control.

---

## Local development

### 1. Clone the repository

```bash
git clone https://github.com/A-Vasili/p_kids_events.git
cd p_kids_events
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Create an Administrator

```bash
python manage.py createsuperuser
```

### 6. Start the development server

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Local development uses SQLite when `DATABASE_URL` is not set.

---

## Environment configuration

Copy `.env.example` only as a reference. Do not commit a real `.env` file.

Important production variables include:

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Secret used by Django for signing and security |
| `DJANGO_DEBUG` | Must be `False` in production |
| `DATABASE_URL` | PostgreSQL connection supplied by Render |
| `DJANGO_ALLOWED_HOSTS` | Permitted hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Trusted HTTPS origins for POST requests |
| `DJANGO_TRUST_PROXY_SSL_HEADER` | Allows Django to recognise Render’s HTTPS proxy |
| `DJANGO_SECURE_SSL_REDIRECT` | Redirects production HTTP requests to HTTPS |
| `DJANGO_SECURE_HSTS_SECONDS` | Enables HTTP Strict Transport Security |
| `DJANGO_MEDIA_ROOT` | Persistent uploaded-media path |
| `DJANGO_SERVE_MEDIA` | Enables the project’s controlled media-serving route |

Never commit real secrets, production database credentials, or demonstration-account passwords.

---

## Testing and checks

Run the complete test suite:

```bash
python manage.py test
```

Run configuration checks:

```bash
python manage.py check
python manage.py makemigrations --check
```

Test static-file collection:

```bash
python manage.py collectstatic --no-input
```

Run Django’s production-oriented checks with appropriate production environment variables:

```bash
python manage.py check --deploy
```

The automated tests cover:

- registration and authentication;
- profile ownership;
- roles and delegated permissions;
- catalogue browsing and filters;
- booking and checkout;
- server-side price validation;
- stale or manipulated session data;
- worker availability and assignments;
- party completion;
- reviews and testimonial privacy;
- recommendations and analytics;
- chat access, unread state, and rate limiting;
- catalogue image validation;
- CSRF and HTML escaping;
- custom management workflows;
- accessibility-related page structure.

The exact test count may increase as regression tests are added, so the command output is the authoritative current result.

---

## Production deployment

The application is deployed on Render using:

- a Python web service;
- Gunicorn;
- managed PostgreSQL;
- WhiteNoise static-file delivery;
- HTTPS;
- a persistent media disk;
- environment variables for configuration and secrets.

`render.yaml` defines the infrastructure. Render runs:

```bash
bash build.sh
```

The build script:

1. installs dependencies;
2. collects static files;
3. applies database migrations;
4. runs Django’s deployment checks.

The web service starts with:

```bash
python -m gunicorn config.wsgi:application \
  --bind 0.0.0.0:$PORT \
  --workers ${WEB_CONCURRENCY:-1}
```

Pushes to the connected GitHub branch trigger a new Render deployment.

---

## Useful routes

| Route | Purpose |
|---|---|
| `/` | Homepage |
| `/party-ideas/` | Searchable catalogue |
| `/party-builder/` | Multi-step party builder |
| `/accounts/sign-up/` | Customer registration |
| `/accounts/sign-in/` | Sign in |
| `/accounts/dashboard/` | Customer dashboard |
| `/accounts/messages/` | Full-page customer chat |
| `/operations/` | Worker operations portal |
| `/management/` | Custom management panel |
| `/management/messages/` | Staff customer-chat inbox |

Access to protected routes depends on the signed-in user’s role and permissions.

---

## Demonstration accounts

Demonstration credentials are intentionally **not** stored in this public repository.

The private submission document should provide temporary credentials for the roles required during assessment, such as:

- Administrator
- Owner
- Worker
- Customer

Passwords should be changed or accounts disabled after marking.

---

## Current limitations

- Payment is simulated; there is no real payment-provider integration.
- Customer chat uses timed polling rather than WebSockets.
- The application does not send email or SMS notifications.
- Automatic assignment runs during the web workflow rather than through a background task queue.
- The recommendation system is rule- and history-based rather than machine-learning based.
- Customer-interface translation is primarily browser-side rather than Django’s full internationalisation framework.
- Uploaded media relies on the configured Render persistent disk.
- Production monitoring and independent off-platform database backups require further configuration.

These limitations do not prevent the project from demonstrating the required catalogue, database, account, security, recommendation, rating, cart, management, and deployment features.

---

## Possible future improvements

- Integrate a PCI-compliant payment provider without storing payment-card details.
- Add email notifications for bookings, assignments, reviews, and chat replies.
- Use Celery and a task broker for background assignment and notification work.
- Add WebSocket chat using Django Channels.
- Store uploaded media in object storage.
- Add GitHub Actions to run tests before deployment.
- Configure scheduled PostgreSQL backups and application monitoring.
- Expand the recommendation explanation shown to customers.
- Move all server-rendered text to Django’s internationalisation framework.
- Add downloadable management reports.

---

## Academic note

This repository was created for the ITC4214 Internet Programming assessment. External libraries and frameworks remain subject to
their respective licences. The project documentation focuses on the code and design decisions implemented for the academic
prototype.
