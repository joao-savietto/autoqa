FROM debian:bookworm-slim

# Install tools needed for setup
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    socat \
    && rm -rf /var/lib/apt/lists/*

# Download and install Chrome for Testing
ARG CHROME_VERSION=148.0.7778.97
RUN wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" -O /tmp/chrome.zip \
    && unzip -q /tmp/chrome.zip -d /opt/ \
    && rm /tmp/chrome.zip \
    && mkdir -p /opt/google \
    && mv /opt/chrome-linux64 /opt/google/chrome

# Install Chrome runtime dependencies from bundled deb.deps
RUN apt-get update \
    && while IFS= read -r pkg; do \
         apt-get satisfy -y --no-install-recommends "$pkg"; \
       done < /opt/google/chrome/deb.deps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 chromeuser && chown -R chromeuser:chromeuser /home/chromeuser /opt/google

USER chromeuser
WORKDIR /home/chromeuser

EXPOSE 9222

# Start socat to forward 0.0.0.0:9222 -> 127.0.0.1:9222, then launch Chrome
# Chrome ignores --remote-debugging-address and binds to 127.0.0.1 only,
# so socat bridges the gap for external access.
ENTRYPOINT ["sh", "-c", \
    "socat TCP-LISTEN:9222,reuseaddr,fork TCP:127.0.0.1:9223 & \
     /opt/google/chrome/chrome \
       --no-sandbox \
       --headless=new \
       --disable-gpu \
       --disable-dev-shm-usage \
       --remote-debugging-port=9223 \
       --remote-debugging-address=127.0.0.1"]
