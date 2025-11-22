FROM grafana/grafana:latest

# Copy provisioning configuration
COPY grafana/provisioning/datasources /etc/grafana/provisioning/datasources
COPY grafana/provisioning/dashboards /etc/grafana/provisioning/dashboards

# Expose port
EXPOSE 3000

# Grafana will start automatically
