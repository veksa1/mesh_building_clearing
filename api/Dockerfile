FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install API + simulation dependencies. numpy from api/requirements is enough;
# we deliberately skip matplotlib (only the matplotlib-driven `run_sim.py` needs it).
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install -r /app/api/requirements.txt

# Copy the swarm_sim package and HTTP shell. The package lives at the repo root
# in this codebase; we mount it under /app/swarm_sim so `from swarm_sim...` works.
COPY __init__.py /app/swarm_sim/__init__.py
COPY agent.py building.py environment.py export_sim.py floorplan_io.py \
     layout_bfs_agent.py navigation.py perception.py propagation.py radio.py \
     room_bfs_plan.py sim_kernel.py viz_comms.py \
     /app/swarm_sim/
COPY api /app/api

ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
