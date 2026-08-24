# Document Studio Bot

A production-oriented asynchronous Telegram bot for real document/image workflows. The UX is inspired by the attached reference screenshot: compact inline menus, status cards, action controls, galleries, pagination, retry/cancel actions, and a persistent history.

The implementation is original. It does not copy the reference bot's branding, text, identity, private code, or implementation.

## Real features

- PDF → page images
- Images → PDF
- Merge PDFs
- Split PDF by page ranges
- Extract text from PDF
- OCR images/PDF pages when Tesseract is installed
- Compress PDF by rebuilding it from rendered pages
- Rotate PDF pages
- Page gallery with pagination
- Download one result
- Download all results as a validated ZIP
- User settings
- Persistent history
- Real job queue, per-user concurrency limit, cancellation and retries
- File integrity validation
- Rate limiting
- Admin tools
- Health endpoint
- Docker + docker-compose support
- Automated cleanup of temporary files

## Requirements

- Python 3.13+
- Telegram Bot Token from @BotFather
- Optional: Tesseract OCR for OCR feature

## Quick start

```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN=...
python -m pip install -r requirements.txt
python bot.py
```

Health check: `http://127.0.0.1:8080/health`

## Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f
```

## License

MIT
