FROM python:3.12-slim-bookworm
# Intentionally has no default acceptance. Owner must approve Microsoft terms.
ARG FOODSAVE_ACCEPT_ODBC_EULA
RUN test "$FOODSAVE_ACCEPT_ODBC_EULA" = "Y" || (echo 'ODBC Driver 18 EULA approval is required before building.' >&2; exit 1)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/msprod.deb \
    && dpkg -i /tmp/msprod.deb && rm /tmp/msprod.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 foodsave
COPY --chown=foodsave:foodsave foodsave ./foodsave
COPY --chown=foodsave:foodsave migrations ./migrations
USER foodsave
EXPOSE 8000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "foodsave.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
