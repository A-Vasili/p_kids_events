# P Kids Events — Django Web Application

## Student details

- Athanasios Vasilis 
- 277690
- ITC4214 Internet Programming 

## About the project

This project is for a children’s event company called "P Kids Events". The aim of the project was to build more than a basic website with static information. It includes a party catalogue, a multi-step booking process, customer accounts, worker scheduling, automatic worker assignment, reviews, analytics, customer chat, and a custom management area.

The project is still an academic/demo application. In particular, the checkout is simulated and no real payment is processed.

The main areas are:

- role-based permissions;
- database transactions and row locking;
- session-based multi-step checkout;
- ORM queries for recommendations and analytics;
- verified reviews and testimonial consent;
- asynchronous JavaScript requests for chat, reviews, and recommendations.

---

## Main features

### Customer features

- View the home, about, gallery, testimonial, and party ideas pages.
- Search and filter party packages and extra experiences.
- Build a party through a multi-step form.
- Complete a simulated checkout using approved test card numbers.
- Create an account, sign in, and save profile information.
- View previous bookings from a customer dashboard.
- Review a completed party using a private review code.
- Choose whether feedback stays private or becomes a public testimonial.
- Send messages to the P Kids Events team through a customer chat widget.
- Change the site theme and switch between supported English and Greek interface text.
### Worker features

- View party offers assigned to the signed-in worker.
- Accept or decline an assignment.
- Add available, preferred, and unavailable time periods.
- View a personal work schedule.
- Mark an accepted party as completed after its event date.
- Use delegated pricing or chat permissions when an Owner or Administrator grants them.

### Owner and Administrator features

- Use a custom management panel instead of Django Admin.
- Manage packages, categories, add-ons, images, and prices.
- View and update bookings.
- Assign or reassign workers manually.
- Manage worker and customer accounts.
- Grant pricing-management and chat-responder permissions.
- View worker schedules and booking conflicts.
- View audit history for important changes.
- View booking, add-on, and review analytics.
- Reply to customer chats.

## Technology used

| Technology I Used in the project | 

| Python 3.12 | Main programming language used during development |
| Django 5.2 | Backend framework, routing, forms, authentication, ORM, sessions, and templates |
| SQLite | Development database |
| HTML and Django Templates | Server-rendered pages |
| CSS and Bootstrap | Layout, responsive design, and reusable interface components |
| Vanilla JavaScript | Theme/language controls, custom form controls, chat polling, recommendations, and AJAX form submissions |
| Pillow | Validation and handling of uploaded catalogue images |

The exact Python dependencies are listed in `requirements.txt`.

## Project structure

popadoo_kidsevents/
|-- accounts/             # Accounts, profiles, roles, and permissions
|-- communications/       # Customer support chat
|-- config/               # Project-wide Django settings and root URLs
|-- core/                 # Public information pages and security middleware
|-- operations/           # Worker portal and management system
|-- party_builder/        # Catalogue, booking, checkout, reviews, and analytics
|-- static/               # CSS, JavaScript, images, SVG files, and local Bootstrap files
|-- templates/            # Shared and app-specific Django templates
|-- manage.py             # Django command-line entry point
|-- requirements.txt      # Python packages required by the project
|-- db.sqlite3            # Local development database

The code is divided into separate Django apps so that each app has one main responsibility. This makes the project easier to understand and avoids putting every feature in one very large app.

# Django apps

## 1. `core`

The `core` app contains the public pages that do not need their own large business module.

### Main responsibilities

- Home page.
- About page.
- Gallery page.
- Public testimonials page.
- Redirects from older URLs.
- Extra browser security headers.

### Important files

| File | Purpose |

| `core/urls.py` | Defines public routes such as `/`, `/about/`, and `/gallery/`. |
| `core/views.py` | Loads approved public testimonials from the database. |
| `core/middleware.py` | Adds Content Security Policy, Permissions Policy, and cross-origin protection headers. |
| `core/tests.py` | Tests public pages, navigation, shared layouts, and security headers. |

The public information pages mainly use Django’s `TemplateView`. A custom `TestimonialsView` is used because testimonials must be
loaded from verified database records rather than being hard-coded in HTML.

## 2. `accounts`

The `accounts` app manages authentication, profiles, and the project’s business roles.

### Main responsibilities

- Customer registration.
- Sign in and sign out.
- Customer profile editing.
- Customer booking dashboard.
- Automatic creation of a `CustomerProfile` for each user.
- Worker profile information.
- Owner, Worker, Pricing Manager, and Chat Responder groups.
- Shared permission helper functions.
- Management commands for creating roles and demonstration accounts.

### Important files

| File | Purpose |

| `accounts/models.py` | Contains `CustomerProfile` and `WorkerProfile`. |
| `accounts/forms.py` | Validates sign-up, sign-in, and profile forms. |
| `accounts/views.py` | Handles account pages and the customer dashboard. |
| `accounts/permissions.py` | Provides reusable role and permission checks. |
| `accounts/signals.py` | Creates profiles and role groups automatically. |
| `accounts/management/commands/` | Contains command-line tools for role setup and demo accounts. |
| `accounts/tests.py` | Tests registration, permissions, escaping, and authentication behaviour. |

### Role design

The application separates these roles:

- **Administrator:** a Django superuser with system-level control.
- **Owner:** a normal user in the `Owners` group who can manage the business but is not automatically a superuser.
- **Worker:** an active user in the `Workers` group with a `WorkerProfile`.
- **Pricing Manager:** a worker who has been given catalogue-management permissions.
- **Chat Responder:** a worker who has been given permission to answer customer chats.
- **Customer:** an active account without a protected staff role.

This separation follows the **principle of least privilege**. A person receives only the permissions needed for their job. For example, a chat responder does not automatically receive access to prices or bookings.

The navigation uses role information to decide which links to display, but the actual views and services repeat the permission checks. Hiding a link is useful for the interface, but it is not treated as security.

## 3. `party_builder`

The `party_builder` app is the largest customer-facing app. It contains the party catalogue, the booking workflow, simulated checkout, reviews, recommendations, and analytics calculations.

### Main responsibilities

- Store package categories and subcategories.
- Store party packages and add-on experiences.
- Display searchable and filterable party ideas.
- Store an unfinished party in the user’s Django session.
- Validate customer and event details.
- Recalculate prices on the server.
- Create completed booking records.
- Generate private review codes.
- Accept verified package and add-on reviews.
- Control whether written feedback is private or public.
- Calculate popularity, ratings, add-on pairs, and recommendations.

### Important files

| File | Purpose |

| `party_builder/models.py` | Main database models for the catalogue, bookings, and reviews. |
| `party_builder/forms.py` | Forms for package selection, customer details, simulated payment, review codes, and reviews. |
| `party_builder/views.py` | Multi-step checkout, review pages, and recommendation JSON endpoint. |
| `party_builder/party_ideas.py` | Public catalogue search, filtering, sorting, detail pages, and session actions. |
| `party_builder/services.py` | Trusted checkout/session logic and booking creation. |
| `party_builder/review_services.py` | Review-code verification, review authorization, saving reviews, and consent handling. |
| `party_builder/analytics.py` | Popularity, ratings, add-on pairs, recommendations, and management reports. |
| `party_builder/validators.py` | Secure image filename and upload validation. |
| `party_builder/migrations/` | Database schema changes and seeded catalogue data. |
| `party_builder/test_*.py` | Tests for checkout, catalogue, reviews, testimonials, recommendations, and analytics. |

### Main database models

- `Category`: groups packages and experiences and supports parent/child categories.
- `PartyPackage`: the main party product, including capacity, duration, price, image, and included experiences.
- `GuestPriceTier`: retained for older booking data and compatibility with earlier versions of the project.
- `AddonExperience`: an optional extra that can add cost and event duration.
- `PartyBuild`: a submitted booking with contact information, event details, prices, status, and assignment state.
- `PartyBuildAddon`: connects a booking to its selected add-ons and stores the price used at checkout.
- `PartyReview`: one verified review for one completed booking.
- `AddonRating`: ratings for the add-ons that were actually included in the reviewed booking.

### Booking flow

The main booking process is:

1.Party Ideas or Builder

2.Select package and add-ons
        
3.Save temporary choices in session
        
4.Enter contact and event details
        
5.Validate simulated payment form
        
6.Recalculate price from database values
        
7.Create PartyBuild and PartyBuildAddon records
        
8.Commit the transaction
        
9.Start automatic worker assignment

Only small temporary values, such as selected database IDs and form details, are kept in the session. The session is cleaned if it contains invalid, duplicated, inactive, or old values.

### Simulated checkout

The payment form accepts approved test card numbers and performs format checks such as the Luhn algorithm. However, the application does **not** store the full card number or security code. It stores only safe demonstration metadata:

- detected card brand;
- last four digits;
- a generated simulated payment reference.

This decision reduces unnecessary sensitive data and makes it clear that the project is not a real payment system.

### Verified review flow

A review can only be submitted when:

1. the user is signed in;
2. the booking belongs to that user;
3. the booking is marked as completed;
4. the correct booking review code is entered;
5. the temporary review authorization has not expired.

The authorization is stored in the session for a limited period. Generic error messages are used so that one customer cannot use the form to discover whether another customer’s review code exists.

A review is private by default. Public testimonial consent is stored separately with a timestamp, and customers may withdraw that consent later.

## 4. `operations`

The `operations` app contains both the worker portal and the custom business management system.

### Main responsibilities

- Worker availability.
- Worker assignment offers.
- Accepting and declining work.
- Worker schedules.
- Automatic worker selection.
- Manual assignment and conflict overrides.
- Booking status changes.
- Catalogue management.
- User and role management.
- Audit logging.
- Management analytics.

### Important files

| File | Purpose |

| `operations/models.py` | Stores availability, assignment history, and audit events. |
| `operations/views.py` | Worker-facing dashboard, assignments, availability, and schedule pages. |
| `operations/management_views.py` | Custom Owner and Administrator management panel. |
| `operations/forms.py` | Worker, catalogue, assignment, booking, and management forms. |
| `operations/services/assignment.py` | Automatic offers, ranking, acceptance, declines, and manual assignment. |
| `operations/services/scheduling.py` | Calculates event times, availability, conflicts, and worker daily load. |
| `operations/services/bookings.py` | Controls valid booking status changes and completion. |
| `operations/services/catalogue.py` | Saves, archives, removes, and audits catalogue records. |
| `operations/services/users.py` | Creates and changes protected user roles safely. |
| `operations/services/audit.py` | Creates consistent audit records. |
| `operations/management_urls.py` | Routes for the custom management area. |
| `operations/tests.py` and `test_management.py` | Tests permissions, assignments, management actions, CSRF, and audit history. |

### Worker assignment process

After a booking has been saved, the assignment service searches for eligible workers. A worker must:

- have an active account;
- have an active `WorkerProfile`;
- belong to the Worker group;
- have an availability window that covers the event;
- have no unavailable period overlapping the event;
- have no accepted booking conflict;
- be below the worker’s maximum parties for that day.

Eligible workers are ranked by:

1. accepted workload on the event date;
2. number of pending offers;
3. the date of their last accepted assignment;
4. worker ID as a final stable tie-breaker.

This attempts to distribute work fairly instead of always selecting the same worker.

If no worker is available, the booking is placed into **manual review** for an Owner or Administrator.

### Concurrency protection

Assignment and booking services use:

- `transaction.atomic()` to make related database changes all-or-nothing;
- `select_for_update()` to lock important rows during a sensitive update;
- database uniqueness constraints to prevent multiple accepted assignments for one booking;
- `transaction.on_commit()` to delay follow-up work until the booking is definitely saved.

These features help prevent race conditions. For example, without row locking, two requests could try to accept or change the same assignment at nearly the same time.

SQLite is suitable for this college project and local development, but a production version with many simultaneous users would normally use a database such as PostgreSQL for stronger concurrency support.

### Custom management area

The project does not enable the standard Django Admin site. Instead, it provides a custom `/management/` area designed around the business workflow.

This was chosen because the project has specific roles and actions, such as:

- archive rather than delete a package that appears in booking history;
- explain why a schedule conflict is being overridden;
- protect the last active Owner account;
- separate pricing permission from chat permission;
- display business-focused booking and analytics pages.

## 5. `communications`

The `communications` app provides customer support messaging.

### Main responsibilities

- One continuing chat for each customer account.
- Messages from customers and approved staff.
- A customer chat page and floating chat widget.
- A management inbox for staff.
- Per-user unread state.
- Basic customer message rate limiting.

### Important files

| File | Purpose |

| `communications/models.py` | Contains chats, messages, and per-user read states. |
| `communications/services.py` | Validates messages, checks permissions, applies rate limits, and updates unread state. |
| `communications/views.py` | Customer, widget, refresh, inbox, and reply endpoints. |
| `communications/forms.py` | Message and management filter forms. |
| `communications/context_processors.py` | Adds chat navigation information to templates. |
| `communications/tests.py` | Tests access control, escaping, rate limits, unread state, and delegation. |
| `static/js/chat-widget.js` | Loads and refreshes the customer chat panel in the browser. |

Each message stores a snapshot of the sender’s displayed name and role. This keeps old conversations understandable even if the account’s name or staff role changes later.

The widget uses `fetch()` and polls for updates approximately every 18 seconds. Polling was simpler to implement and deploy for this project than WebSockets. A larger real-time system could use Django Channels and WebSockets in a future version.

Customers are limited to 10 messages within 5 minutes. This is a simple burst limit intended to reduce accidental spam; it is not a complete anti-abuse system.

# Important project-wide files


## `config/settings.py`

This file controls project-wide behaviour, including:

- installed Django apps;
- middleware;
- template folders and context processors;
- SQLite database configuration;
- timezone (`Europe/Athens`);
- static and uploaded media locations;
- authentication redirects;
- cookie and browser security settings;
- environment-variable configuration.

Important environment variables include:

| Variable | Purpose |

| `DJANGO_SECRET_KEY` | Secret value used by Django. A strong value is required in production. |
| `DJANGO_DEBUG` | Enables or disables debug mode. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names accepted by Django. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Trusted HTTPS origins for deployed forms. |
| `DJANGO_SECURE_SSL_REDIRECT` | Controls automatic HTTPS redirection. |

Development values are provided so the project can run locally. They should not be copied directly into a real deployment.

## `config/urls.py`

This is the root URL configuration. It includes the routes from all five apps and keeps exact chat/management routes before broader URL groups where necessary.

## `templates/base.html`

This is the shared public-page layout. It loads:

- metadata;
- navigation;
- Django messages;
- the main content block;
- footer;
- optional customer chat widget;
- shared CSS and JavaScript.

Other templates extend this file instead of repeating the whole HTML document.

## `static/`

The static folder contains:

- local Bootstrap files;
- project CSS files;
- JavaScript files;
- package and add-on artwork;
- gallery and team images;
- SVG icons and logo.

Bootstrap is stored locally, which allows the project’s strict Content Security Policy to avoid relying on third-party content delivery networks.

## `migrations/`

Migrations describe changes to the database structure over time. Some `party_builder` migrations also seed the initial catalogue. The current seeded catalogue is tested to contain eight packages and twenty add-on experiences.

Migration files should normally not be edited after they have been applied. New database changes should be created with a new migration.

# Main coding decisions and reasons

## 1. Separate apps by responsibility

The project is divided into apps instead of placing all models and views together. This keeps related code close and makes responsibilities clearer.

For example, the booking app does not directly contain worker availability logic, and the chat app does not contain catalogue code.

## 2. Use a service layer for important business actions

Views mainly deal with HTTP requests and responses. Important changes are placed in service files, including:

- creating a booking;
- assigning a worker;
- changing booking status;
- saving reviews;
- managing roles;
- removing catalogue records;
- sending chat messages.

This avoids very large views and allows the same validation and permission rules to be reused from different pages or future APIs/commands.

## 3. Recalculate prices on the server

The browser sends the selected package and add-on IDs, but it is not trusted to provide the final price. The server loads the active database records and recalculates the total using `Decimal` values.

This prevents a user from editing browser data to submit a cheaper price.

## 4. Store price snapshots in completed bookings

Package and add-on prices may change later. A completed booking stores the price used at checkout, including each selected add-on’s unit price.

Without snapshots, an old booking could appear to have a different total after a manager changes the catalogue.

## 5. Archive records that are part of history

Packages, categories, or add-ons that have already been used may need to remain in the database so old bookings still make sense. The management services decide whether an unused record can be deleted or a referenced record should be made inactive.

Several foreign keys also use `PROTECT`, which prevents important historical records from being removed accidentally.

## 6. Use multiple validation layers

The project validates data in several places:

- browser attributes provide immediate guidance;
- Django forms validate user input;
- services repeat important permission and business checks;
- model `clean()` methods validate relationships between fields;
- database constraints enforce rules even if a future code path forgets a form check.

No single layer is treated as enough on its own.

## 7. Use UUIDs for public booking and chat URLs

Bookings and chats use UUID values in public URLs instead of exposing small sequential database IDs. This makes URLs harder to guess. UUIDs do not replace permission checks, so ownership and role checks are still required.

## 8. Keep a human-readable review code

Each booking receives a separate review code that is easier for a customer to enter than a UUID. The code is normalized before storage and checked together with the signed-in user and booking status.

## 9. Preserve audit history

Sensitive management actions create `AuditEvent` records with the actor, action type, target, summary, and safe before/after values.

The audit system intentionally avoids copying sensitive information such as full review comments, review codes, passwords, or payment details into the log.

## 10. Build security into the shared configuration

The project uses Django’s built-in protections and additional configuration, including:

- CSRF protection for state-changing forms and AJAX requests;
- escaped template output to reduce cross-site scripting risk;
- secure password hashing and password validators;
- permission checks in both views and services;
- HTTP-only and SameSite session cookies;
- clickjacking protection;
- Content Security Policy;
- upload size limits;
- image type, extension, and size validation.

## 11. Use progressive enhancement in JavaScript

Django forms and links remain the main source of submitted data. JavaScript improves the interface with custom controls, AJAX, polling, translations, and dynamic recommendations.

Important values such as permissions, prices, user identity, and database changes remain controlled by Django on the server.

## 12. Include accessibility features

The project includes features such as:

- one main landmark per page;
- a “skip to main content” link;
- visible labels and field errors;
- `aria-live` status messages;
- keyboard support for custom controls;
- alternative text for catalogue images;
- accessible radio buttons and navigation controls;
- focus management in interactive components.

Accessibility is handled in templates, forms, JavaScript, and CSS rather than being added only at the end.

# Database relationship overview

Django User
|-- CustomerProfile (one-to-one)
|-- WorkerProfile (optional one-to-one)
|-- PartyBuild bookings (one-to-many)
|-- CustomerChat (maximum one per customer)

Category
|-- child Categories
|-- PartyPackages
|-- AddonExperiences

PartyBuild
|-- one PartyPackage
|-- selected AddonExperiences through PartyBuildAddon
|-- PartyAssignments
|-- maximum one PartyReview

PartyReview
|-- AddonRatings for add-ons from the same booking

CustomerChat
|-- ChatMessages
|-- ChatReadStates for individual users

Useful local routes include:

| Route | Area |

| `/` | Public home page |
| `/party-ideas/` | Searchable party catalogue |
| `/party-builder/` | Multi-step party builder |
| `/accounts/sign-up/` | Customer registration |
| `/accounts/dashboard/` | Customer booking dashboard |
| `/operations/` | Worker operations area |
| `/management/` | Owner/Administrator custom management area |
| `/management/messages/` | Staff customer-chat inbox |

Access to protected routes depends on the signed-in account’s role.

# Running tests

Run all automated tests with:

```bash
python manage.py test
```

The project currently contains **251 tests**, and they pass with Django’s system check reporting no issues.

The tests cover areas including:

- registration and login;
- role permissions;
- booking and checkout;
- server-side pricing;
- session tampering and stale data;
- worker availability and assignment;
- booking completion;
- catalogue management;
- CSRF and HTML escaping;
- image validation;
- reviews and testimonial consent;
- recommendations and analytics;
- chat access, unread state, and rate limiting;
- page structure and accessibility-related markup.

Tests were important in this project because many features depend on combinations of permissions, booking status, assignment status, and dates.

# Current limitations

This is a college project, so some decisions are suitable for demonstration but would need more work for production.

- Payments are simulated; there is no Stripe, PayPal, or bank integration.
- Local development uses SQLite, while the deployment configuration uses PostgreSQL through `DATABASE_URL`.
- Customer chat uses timed polling rather than WebSockets.
- The message rate limit is stored and calculated in the application database, not a dedicated service such as Redis.
- There is no email or SMS notification system for bookings, assignments, or chat replies.
- Static files are prepared for WhiteNoise, while uploaded media requires the configured persistent Render disk.
- Render deployment is configured, while advanced monitoring and independent off-platform backups remain future improvements.
- The translation system mainly uses browser-side translation data rather than Django’s full translation framework.
- Automatic worker assignment runs after checkout in the web application process instead of a background task queue.

These limitations do not stop the project from demonstrating the required workflows, but they are areas that could be improved in a larger version.

# Possible future improvements

- Connect the checkout to a real PCI-compliant payment provider without storing card data in Django.
- Move the database to PostgreSQL.
- Use Django Channels and WebSockets for real-time chat.
- Add email notifications for booking confirmations and worker offers.
- Move assignment and notification work to a background queue such as Celery.
- Store media in a cloud object-storage service.
- Add automated deployment and continuous integration.
- Expand the recommendation system with more booking data and clearer explanation of why an item was suggested.
- Use Django’s internationalization tools for fully translated server-rendered content.
- Add more reporting exports for Owners.

# Final note

A customer can discover a package, build and submit a booking, receive a worker assignment in the system, communicate with staff, and later leave a verified review. Workers and managers see different interfaces and permissions, while important changes are validated, recorded, and tested on the server.

# Render deployment

The repository includes a focused production configuration for Render. Local
development still uses SQLite, while Render supplies PostgreSQL through the
`DATABASE_URL` environment variable. WhiteNoise serves the collected CSS,
JavaScript, and bundled catalogue artwork. A persistent disk mounted at
`/opt/render/project/src/media` preserves images uploaded through management.

The deployment files are:

- `render.yaml` — describes the web service, PostgreSQL database, environment,
  and media disk;
- `build.sh` — installs dependencies, collects static files, applies migrations,
  and performs Django's deployment check;
- `.python-version` — keeps Render on Python 3.13;
- `.env.example` — lists configuration names without storing real secrets.

To verify the production configuration locally without changing the normal
development database, run the following commands from an activated virtual
environment:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test
python manage.py collectstatic --no-input
```

Render deployment uses `./build.sh` as the build command and starts the site
with:

```bash
python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Production secrets belong in Render's environment settings. Never commit a
real `.env` file, database password, demo-account password, or Django secret
key to GitHub. Custom domains must also be added to
`DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
