FROM python:3.11-slim

WORKDIR /app

# Optimize build times by copying dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application stack
COPY . .

# Google Cloud Run expects the app to listen on the dynamic $PORT environment variable.
# We set a standard fallback to 8080.
ENV PORT=8080
EXPOSE ${PORT}

# Run Streamlit on the specified container port, disable CORS to avoid GCP origin issues, and run on 0.0.0.0
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.enableCORS=false --browser.gatherUsageStats=false
