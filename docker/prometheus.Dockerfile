FROM prom/prometheus:latest

# Copy configuration files
COPY prometheus/prometheus.yml /etc/prometheus/prometheus.yml
COPY prometheus/alert_rules.yml /etc/prometheus/alert_rules.yml

# Expose port
EXPOSE 9090

# Start Prometheus
CMD ["--config.file=/etc/prometheus/prometheus.yml", \
     "--storage.tsdb.path=/prometheus", \
     "--web.console.libraries=/etc/prometheus/console_libraries", \
     "--web.console.templates=/etc/prometheus/consoles", \
     "--web.enable-lifecycle"]
