FROM python:3.13-slim

WORKDIR /app

# Python dependencies (only what the MCP server needs)
COPY mcp_server/requirements.txt /app/mcp_server/requirements.txt
RUN pip install --no-cache-dir -r mcp_server/requirements.txt

# Copy only the MCP server code
COPY mcp_server/ ./mcp_server/

# Create non-root user
RUN adduser --disabled-password --no-create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 3157

CMD ["python", "mcp_server/server.py"]
