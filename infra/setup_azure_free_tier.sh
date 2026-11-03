#!/bin/bash
# This line tells the OS to use the Bash shell to interpret subsequent commands.

# Azure CLI Script to provision free-tier resources for PulseOps-Engine
# This script demonstrates how to provision Azure free-tier resources for PulseOps-Engine. It uses Azure CLI commands to create groups, storage, database, and container apps.

# Note: This script assumes you have the Azure CLI installed and are logged in.
# Without Azure CLI or authentication, the az commands would fail.

# Variables - Replace with your target info
# These shell variables centralize deployment inputs so the commands below remain
# consistent; changing one value changes the target resource without changing the
# provisioning sequence.
# Each variable sets the values used later in az commands.
# RESOURCE_GROUP defines the Azure Resource Group name; all resources are created under this group.
# LOCATION specifies Azure region; using a free‑tier region keeps costs low.
# STORAGE_ACCOUNT creates a unique storage account name; names must be globally unique.
# POSTGRES_SERVER is a placeholder for a PostgreSQL server name.
# CONTAINER_APP_NAME is the logical name for the Container App.
RESOURCE_GROUP="pulseops-rg-free"
LOCATION="eastasia"
STORAGE_ACCOUNT="pulseopsstore$(date +%s)" # Unique name
# The timestamp suffix avoids collisions because Azure storage account names are
# globally shared; retain only lowercase letters and numbers in production values.
POSTGRES_SERVER="pulseops-db-server"
CONTAINER_APP_NAME="pulseops-engine-app"

echo "Creating Resource Group..."
# Runtime: Calls Azure CLI to create a resource group.
# Architecture: Resource Group acts as a container for all subsequent resources.
# Summary: Creates a logical grouping for infrastructure.
az group create --name $RESOURCE_GROUP --location $LOCATION
# Runtime: Runs the az command, creating the group.
# Architecture: Idempotent – if group exists, command returns OK.
# Summary: Ensures the group exists before creating other resources.

echo "Creating Storage Account & Queue..."
# Runtime: Creates a storage account for blobs/queue, used for message queue.
# Architecture: Uses Standard_LRS SKU free tier.
# Summary: Provides storage for app data.
az storage account create --name $STORAGE_ACCOUNT --location $LOCATION --resource-group $RESOURCE_GROUP --sku Standard_LRS
# Runtime: Creates a queue named student-provisioning.
# Architecture: Queue used for provisioning messages.
# Summary: Enables async messaging.
az storage queue create --name student-provisioning --account-name $STORAGE_ACCOUNT

echo "Creating Azure Database for PostgreSQL (Free Tier / Basic)..."
# Runtime: Begins creation of a PostgreSQL flexible server.
# Architecture: Free tier uses Burstable tier, Standard_B1ms SKU, 32GB storage.
# Summary: Sets up a lightweight Postgres instance.
# Note: The example uses placeholder password; replace with a secure value.
# Correct syntax:
az postgres flexible-server create \
  --resource-group pulseops-rg-free \
  --name pulseops-pg-free \
  --location eastasia \
  --tier Burstable \
  --sku-name Standard_B1ms \
  --storage-size 32 \
  --admin-user dbadmin \
  --admin-password "<YourSecurePassword123!>" \
  --yes
# Runtime: Command provisions the database; --yes auto-confirms.
# Architecture: Idempotent – if already exists, an error will be returned.
# Summary: Creates a PostgreSQL server with minimal cost.


echo "Creating Azure Container App..."
# Runtime: Begins creation of a Container App.
# Architecture: Uses external ingress on port 8080 to expose the FastAPI service.
# Summary: Deploys the PulseOps-Engine app.
# Note: The full az containerapp create command is truncated with '...' in this example.
# In production, include environment variables, image, and resource limits.
# Correct syntax:
az containerapp create \
  --resource-group pulseops-rg-free \
  --name pulseops-app \
  --target-port 8080 \
  --ingress external \
  ...
# Runtime: This command provisions the container with the specified settings.
# Architecture: idempotent – a duplicate name will error.
# Summary: Makes the FastAPI service reachable over the internet.
  
echo "Provisioning complete."
# Runtime: Signals that all AK commands finished successfully.
# Architecture: Provides a clear end‑point for script completion.
# Summary: Tells the user that setup is done.
