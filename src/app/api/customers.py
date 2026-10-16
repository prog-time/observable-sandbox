import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Customer
from app.schemas import CustomerCreate, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])
logger = logging.getLogger(__name__)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(data: CustomerCreate, session: Session = Depends(get_session)):
    customer = Customer(name=data.name, email=data.email)
    session.add(customer)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.warning("customer email already exists", extra={"email": data.email})
        raise HTTPException(409, "Customer with this email already exists")
    session.refresh(customer)
    logger.info("customer created", extra={"customer_id": customer.id})
    return customer


@router.get("", response_model=list[CustomerOut])
def list_customers(limit: int = 50, session: Session = Depends(get_session)):
    return session.scalars(select(Customer).order_by(Customer.id).limit(limit)).all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, session: Session = Depends(get_session)):
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer
