FROM python:3.14-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_URL=sqlite:////data/subledger.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system subledger \
    && useradd --system --gid subledger subledger \
    && mkdir /data && chown subledger:subledger /data
COPY --chown=subledger:subledger . .
USER subledger
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
