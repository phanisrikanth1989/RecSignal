"""
routes/servers.py — CRUD endpoints for server registration.
"""

import logging
from typing import Optional

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.models import Environment, ServerCreate, ServerResponse, ServerType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/servers", tags=["Servers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_server(row) -> dict:
    return {
        "id": row[0],
        "hostname": row[1],
        "environment": row[2],
        "type": row[3],
        "active": bool(row[4]),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ServerResponse])
def list_servers(
    environment: Optional[Environment] = Query(None, description="Filter by environment"),
    server_type: Optional[ServerType] = Query(None, alias="type", description="Filter by server type"),
    active_only: bool = Query(True, description="Return only active servers"),
    con: oracledb.Connection = Depends(get_db),
):
    """
    Return all registered servers with optional filters.
    """
    sql = "SELECT id, hostname, environment, type, active FROM servers WHERE 1=1"
    params: dict = {}

    if environment:
        sql += " AND environment = :env"
        params["env"] = environment.value

    if server_type:
        sql += " AND type = :stype"
        params["stype"] = server_type.value

    if active_only:
        sql += " AND active = 1"

    sql += " ORDER BY environment, hostname"

    cursor = con.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return [_row_to_server(r) for r in rows]


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, con: oracledb.Connection = Depends(get_db)):
    """Return a single server by ID."""
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, hostname, environment, type, active FROM servers WHERE id = :sid",
        {"sid": server_id},
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Server {server_id} not found")
    return _row_to_server(row)


@router.post("/", response_model=ServerResponse, status_code=201)
def register_server(payload: ServerCreate, con: oracledb.Connection = Depends(get_db)):
    """
    Register a new server.
    Returns the existing record if hostname already exists.
    """
    cursor = con.cursor()

    # Upsert: return existing if already registered
    cursor.execute(
        "SELECT id, hostname, environment, type, active FROM servers WHERE hostname = :hn",
        {"hn": payload.hostname},
    )
    existing = cursor.fetchone()
    if existing:
        return _row_to_server(existing)

    new_id_var = cursor.var(int)
    cursor.execute(
        """
        INSERT INTO servers (hostname, environment, type, active)
        VALUES (:hostname, :env, :stype, :active)
        RETURNING id INTO :new_id
        """,
        {
            "hostname": payload.hostname,
            "env": payload.environment.value,
            "stype": payload.type.value,
            "active": 1 if payload.active else 0,
            "new_id": new_id_var,
        },
    )
    val = new_id_var.getvalue()
    new_id = int(val[0] if isinstance(val, list) else val)
    logger.info("Registered new server: %s (id=%d)", payload.hostname, new_id)
    return {**payload.dict(), "id": new_id}


@router.patch("/{server_id}/deactivate", response_model=ServerResponse)
def deactivate_server(server_id: int, con: oracledb.Connection = Depends(get_db)):
    """Mark a server as inactive (soft-delete)."""
    cursor = con.cursor()
    cursor.execute(
        "UPDATE servers SET active = 0 WHERE id = :sid",
        {"sid": server_id},
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Server {server_id} not found")
    return get_server(server_id, con)
