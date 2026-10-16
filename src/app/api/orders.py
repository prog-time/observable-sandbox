import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.metrics import ORDER_STATUS_CHANGES, ORDERS_CREATED
from app.models import ALLOWED_TRANSITIONS, Customer, Order, OrderStatus
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(data: OrderCreate, session: Session = Depends(get_session)):
    if session.get(Customer, data.customer_id) is None:
        logger.warning("order for unknown customer", extra={"customer_id": data.customer_id})
        raise HTTPException(404, "Customer not found")
    order = Order(customer_id=data.customer_id, amount=data.amount, status=OrderStatus.NEW)
    session.add(order)
    session.commit()
    session.refresh(order)
    ORDERS_CREATED.inc()
    logger.info(
        "order created",
        extra={"order_id": order.id, "customer_id": order.customer_id, "amount": str(order.amount)},
    )
    return order


@router.get("", response_model=list[OrderOut])
def list_orders(
    status: OrderStatus | None = None,
    customer_id: int | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    query = select(Order).order_by(Order.id.desc()).limit(limit)
    if status is not None:
        query = query.where(Order.status == status)
    if customer_id is not None:
        query = query.where(Order.customer_id == customer_id)
    return session.scalars(query).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int, data: OrderStatusUpdate, session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    current = OrderStatus(order.status)
    if data.status not in ALLOWED_TRANSITIONS[current]:
        logger.warning(
            "invalid order status transition",
            extra={"order_id": order_id, "from_status": current, "to_status": data.status},
        )
        raise HTTPException(409, f"Cannot change status from {current} to {data.status}")
    order.status = data.status
    session.commit()
    session.refresh(order)
    ORDER_STATUS_CHANGES.labels(to_status=data.status).inc()
    logger.info(
        "order status changed",
        extra={"order_id": order_id, "from_status": current, "to_status": data.status},
    )
    return order
