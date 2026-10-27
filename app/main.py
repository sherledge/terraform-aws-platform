import os
import time
import logging
from fastapi import FastAPI, Response, HTTPException
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import psycopg

app = FastAPI(title="Infrastructure Benchmark App")

# Prometheus Metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP Request Latency", ["endpoint"])

logging.basicConfig(level=logging.INFO)

def get_db_connection():
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "appdb")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    
    return psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_pass,
        port=db_port,
        connect_timeout=3
    )

@app.middleware("http")
async def track_metrics(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code
    ).inc()
    
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
    return response

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Multi-environment Platform API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/db-check")
def db_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT NOW();")
        db_time = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"status": "database_connected", "timestamp": str(db_time[0])}
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

@app.get("/slow")
def simulate_slow_response(delay: int = 3):
    time.sleep(delay)
    return {"status": "completed", "delay_seconds": delay}

@app.get("/crash")
def simulate_crash():
    logging.critical("Simulated application panic triggered.")
    os._exit(1)