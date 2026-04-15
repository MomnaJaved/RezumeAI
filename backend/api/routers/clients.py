from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Client, Job
from api.schemas import ClientCreate, ClientRead, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientRead])
def list_clients(status: str = "", db: Session = Depends(get_db)):
    q = (
        db.query(
            Client,
            func.count(Job.id).label("active_jobs"),
        )
        .outerjoin(Job, (Job.client_id == Client.id) & (Job.status == "active"))
        .group_by(Client.id)
        .order_by(Client.created_at.desc())
    )
    st = (status or "").strip().lower()
    if st:
        if st not in ("active", "inactive"):
            raise HTTPException(status_code=422, detail="status must be one of: active, inactive")
        q = q.filter(Client.status == st)
    rows = q.all()
    out: list[ClientRead] = []
    for c, n in rows:
        cr = ClientRead.model_validate(c)
        cr.active_jobs = int(n or 0)
        out.append(cr)
    return out


@router.post("", response_model=ClientRead, status_code=201)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    st = (body.status or "active").strip().lower()
    if st not in ("active", "inactive"):
        raise HTTPException(status_code=422, detail="status must be one of: active, inactive")
    existing = db.query(Client).filter(Client.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Client with this name already exists")
    c = Client(
        name=name,
        contact_person=(body.contact_person or "").strip(),
        email=(body.email or "").strip(),
        company_name=(body.company_name or "").strip(),
        status=st,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    cr = ClientRead.model_validate(c)
    cr.active_jobs = 0
    return cr


@router.get("/{client_id}/jobs")
def jobs_for_client(client_id: UUID, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    jobs = (
        db.query(Job)
        .filter(Job.client_id == c.id)
        .order_by(Job.created_at.desc())
        .all()
    )
    # Return same JobRead as jobs router would.
    from api.schemas import JobRead

    out = []
    for j in jobs:
        jr = JobRead.model_validate(j)
        jr.client_name = c.name
        out.append(jr)
    cr = ClientRead.model_validate(c)
    cr.active_jobs = int(
        db.query(func.count(Job.id)).filter(Job.client_id == c.id, Job.status == "active").scalar() or 0
    )
    return {"client": cr, "jobs": out}


@router.patch("/{client_id}", response_model=ClientRead)
def update_client(client_id: UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    upd = body.model_dump(exclude_unset=True)
    if "name" in upd and upd["name"] is not None:
        name = (upd["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        existing = db.query(Client).filter(Client.name == name, Client.id != c.id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Client with this name already exists")
        c.name = name
    if "contact_person" in upd and upd["contact_person"] is not None:
        c.contact_person = (upd["contact_person"] or "").strip()
    if "email" in upd and upd["email"] is not None:
        c.email = (upd["email"] or "").strip()[:320]
    if "company_name" in upd and upd["company_name"] is not None:
        c.company_name = (upd["company_name"] or "").strip()
    if "status" in upd and upd["status"] is not None:
        st = (upd["status"] or "").strip().lower()
        if st not in ("active", "inactive"):
            raise HTTPException(status_code=422, detail="status must be one of: active, inactive")
        c.status = st

    db.commit()
    db.refresh(c)
    cr = ClientRead.model_validate(c)
    cr.active_jobs = int(
        db.query(func.count(Job.id)).filter(Job.client_id == c.id, Job.status == "active").scalar() or 0
    )
    return cr


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: UUID, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(c)
    db.commit()
    return None

