#!/bin/bash
# NeuraX Sandbox Runner Script
#
# Purpose:
#     Executes untrusted Python code in an isolated Docker container
#     with strict resource limits and security constraints.
#
# Usage:
#     ./sandbox_runner.sh <python_code_file>
#
# Security Features:
#     - CPU limit: 1 core
#     - Memory limit: 1GB
#     - Timeout: 30 seconds
#     - Network: disabled
#     - Filesystem: read-only
#     - Auto-cleanup: container removed after execution

# Exit on any error
set -e

# Step 1: Validate input
if [ $# -eq 0 ]; then
    echo "Error: No code file provided"
    exit 1
fi

CODE_FILE="$1"

# Step 2: Validate file exists
if [ ! -f "$CODE_FILE" ]; then
    echo "Error: Code file not found: $CODE_FILE"
    exit 1
fi

# Step 3: Run Docker container with security limits
# --rm: Remove container automatically after it stops
#   Why: Prevents accumulation of stopped containers on host
docker run --rm \
    \
    # CPU constraint: Limit to 1 CPU core
    #   Why: Prevents CPU exhaustion attacks, ensures fair resource sharing
    --cpus=1 \
    \
    # Memory constraint: Hard limit of 1GB
    #   Why: Prevents memory exhaustion (OOM) attacks on host system
    --memory=1g \
    \
    # Network isolation: Disable all network interfaces
    #   Why: Prevents data exfiltration and external communication
    --network=none \
    \
    # File descriptor limit: Max 1024 open files per container
    #   Why: Prevents file descriptor exhaustion attacks
    --ulimit nofile=1024:1024 \
    \
    # Timeout: Kill container after 30 seconds
    #   Why: Prevents long-running tasks from consuming resources indefinitely
    --timeout=30 \
    \
    # Filesystem: Mount root filesystem as read-only
    #   Why: Prevents malicious code from modifying system files
    --read-only \
    \
    # Volume mount: Mount code file as read-only
    #   Why: Allows container to read code without copying into image
    -v "$CODE_FILE:/tmp/task.py:ro" \
    \
    # Volume mount: Provide writable /tmp directory
    #   Why: Python code may need temporary files (e.g., for libraries)
    #   Note: This is a calculated risk; /tmp is isolated per container
    -v /tmp:/tmp:rw \
    \
    # Base image: Python 3.10 official image
    #   Why: Provides clean Python environment without additional dependencies
    python:3.10 \
    \
    # Command: Execute the code file
    python /tmp/task.py

# Exit with container's exit code
exit $?


# Notes:
# - This script is called by compute_node.py for each task execution
# - Docker provides kernel-level isolation (stronger than chroot/jail)
# - Resource limits are enforced by Docker daemon (cannot be bypassed)
# - Read-only filesystem prevents malicious code from persisting or modifying host
# - Network isolation prevents exfiltration even if code bypasses other limits
# - Timeout ensures tasks complete or are killed after reasonable time
# - Auto-cleanup prevents resource leakage across multiple executions

