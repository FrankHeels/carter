# Carter

Small Django storefront project with a product catalog, session-based cart, and guest checkout flow.

## Stack

- Python
- Django 5.2
- Django templates
- SQLite for local development
- `python-decouple` for environment variables

## Project Layout

- `config/` - Django project config and settings package
- `shop/` - catalog, product detail pages, and catalog models
- `cart/` - session cart logic, cart views, and cart tests
- `orders/` - checkout flow, order snapshots, and order tests

## Local Setup

### 1. Create a virtual environment

Windows:

```powershell
python -m venv .venv
```

Unix:

```bash
python3 -m venv .venv
```

### 2. Activate the virtual environment

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Unix:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Create the local environment file

Copy `.env.example` to `.env` and replace the placeholder values.

Windows:

```powershell
Copy-Item .env.example .env
```

Unix:

```bash
cp .env.example .env
```

Required variables:

- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `TELEGRAM_NOTIFICATIONS_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_MANAGER_CHAT_IDS`
- `TELEGRAM_NOTIFICATION_RETRY_MINUTES`

### 5. Run database migrations

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

### 6. Start the development server

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

## Tests

Run Django checks:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.settings.test
```

Run the cart test module:

```powershell
.\.venv\Scripts\python.exe manage.py test cart.tests --settings=config.settings.test
```

Run the orders test module:

```powershell
.\.venv\Scripts\python.exe manage.py test orders.tests --settings=config.settings.test
```

## Telegram Notifications

Order Telegram delivery uses a database outbox and a Django management command. Checkout creates pending notification rows; the command sends only due `pending` and `failed` rows, so no Celery or Redis is required.

Configure Telegram in `.env`:

- `TELEGRAM_NOTIFICATIONS_ENABLED` - set to `True` to create notification rows during checkout.
- `TELEGRAM_BOT_TOKEN` - Telegram bot token used for `sendMessage`.
- `TELEGRAM_MANAGER_CHAT_IDS` - comma-separated manager chat ids.
- `TELEGRAM_NOTIFICATION_RETRY_MINUTES` - delay before a pending or failed notification is due.

Run the processor manually:

```powershell
.\.venv\Scripts\python.exe manage.py process_telegram_notifications
```

Linux cron example:

```cron
* * * * * cd /srv/carter && ./.venv/bin/python manage.py process_telegram_notifications
```

## Notes

- Local runtime artifacts such as `.venv/`, `db.sqlite3`, `media/`, `.playwright-mcp/`, and `md/` are intentionally excluded from version control.
- Development settings load secrets and environment-specific values from `.env`.
- Test runs use `config.settings.test` so they do not depend on local `.env` values.
