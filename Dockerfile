# Production image for the Inventory Planner webapp (webapp/app.py), including
# the mounted read-only MCP server (webapp/mcp_server.py, /mcp).
#
# `scm_agent`, `jobs`, `webapp`, `warehouse` are imported relative to the repo
# root (sys.path, not a setuptools package) - PYTHONPATH=/app plus WORKDIR /app
# reproduces that. Only `src` is an actual installed package (see
# [tool.setuptools] in pyproject.toml), via `pip install -e .`.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY . .

# [web] = fastapi/uvicorn/python-multipart, [mcp] = the mcp package - both are
# hard imports of webapp/app.py (it unconditionally mounts /mcp), not optional.
# [pricing-intel,dataquality] = extruct/lxml/price-parser/chompjs/rapidfuzz/
# python-stdnum, needed for the price_intelligence/price_watch tools and the
# public POST /api/demo-price-scan lead magnet (webapp/demo_price_scan.py) to
# actually run instead of raising ExtractionDependencyMissing/
# PriceParserUnavailable uncaught (an unhandled 500 for a real visitor). Safe
# to add post-#155/#156: every import from these extras is now lazy-loaded
# (src/pricing_intel/extract.py, normalize.py, match/*.py) and the `prod-boot`
# CI job (.github/workflows/tests.yml) guards against a future regression of
# the original bs4 ModuleNotFoundError boot crash.
RUN pip install -e ".[web,mcp,pricing-intel,dataquality]"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn webapp.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
